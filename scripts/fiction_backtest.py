"""FICTION BACKTEST = AMNESIA-2, model-agnostic (2026-09-28).

Owner, 2026-09-28: "opus now is a great LLM and can be used for predicting more
accurately ... using that day's data, I want the engine and LLM to make a
prediction (by making up a scenario and changing names and the contexts so it
makes a fiction choice ...)". And: "converting non numerical data such as human
emotions, news psychology to data with llm is important."

WHAT ALREADY EXISTED (not rebuilt here)
---------------------------------------
* TRIAL-LLM-AMNESIA-1/1B (2026-08-08, sibling repo `Aegis module`): named /
  instructed / masked / synthetic arms + the identification and recall
  canaries. Masking held (0 of 240 identified); synthetic == masked within
  0.0004 Brier; the instruction to forget did nothing; the TASK (12-month
  relative return from five percentiles) was unlearnable, so its verdict named
  AMNESIA-2 = short-horizon reactions around dated events as the next step.
  Nobody ran it. This script is that run.
* `backend/services/leakage_probe.py` (TRIAL-LEAK-1): `masking_violations`,
  the pre-call scan that REFUSES a leaking prompt. Imported, unchanged.
* `backend/services/protocol_p16.py`: `ece` (P4). Imported, unchanged.
* `scripts/exp_llm_blind_gap_2026_09_28.py` (X2, today): `name_aliases`,
  `blind_text`, `leaks`, `price_summary`, `wilson`, `_date_block`,
  `load_titles`, `load_typed`, and its measured DeepSeek cutoff (2025-12).
  Imported, unchanged.

VENDORED (copied, because commits move between repos only by hand)
------------------------------------------------------------------
From `C:/Users/mrthn/Aegis module/aegis_brain/llm/amnesia.py`,
sha256 ce07f68556149098eca01117079accea131de906f144ea91f2ab6d6b89beaf5d:
`FAKE_PREFIX`, `FAKE_SUFFIX`, the `fake_identity` rule (hash -> fabricated
name, ticker, a year 2100+ "unambiguously outside any training corpus"), the
A3 "[SIMULATED SCENARIO ...]" framing, the two canary wordings and the
tolerant `parse_json` used for CANARIES only. Arm A1 (named + "forget"
instruction) is NOT re-run: AMNESIA-1 measured it at zero effect.

WHAT IS NEW
-----------
1. Arms behind one interface, `answer(system, user, case_id) -> dict`, so the
   SAME masked test runs on any model: DeepSeek (the one capped route,
   `llm_analyzer.call_named`), NVIDIA NIM free tier, local (built, never
   starts a server), and a FILE arm through which a model with no API key here
   (Claude Opus as sub-agents of the orchestrator) takes the same test from
   case files, with the mapping sealed away from it.
2. The task: 5-session reaction around an 8-K item 2.02 (earnings) filing,
   where a baseline has measurable signal (trailing volatility AND the stock's
   own past earnings reactions).
3. The answer: three scenarios with probabilities and return ranges, P(beat
   the median stock) at 5 and 21 sessions, a central estimate and an 80%
   range, what would change the view, and four text features scored 0-1
   (novelty, emotional intensity, management confidence, crowdedness), parsed
   by a STRICT schema: a reply that does not parse is refused and counted.
4. A3 keeps every ratio: absolute prices and sizes are rescaled by a random
   factor per case, dates carry a fabricated year (shifted by a constant, so
   intervals and month names stay true).
5. Grading against live baselines, by arm x level x part, with week-block SEs.

Licence: PRODUCT_EXPERIMENT (no claim). Registration:
docs/TRIALS/TRIAL-AMNESIA-2-event-reaction-model-agnostic.md (written before the
first call; its sha256 is stamped into the run's plan).

    python -m scripts.fiction_backtest plan --run R --part clean
    python -m scripts.fiction_backtest plan --run R --part backtest
    python -m scripts.fiction_backtest probe-nvidia --run R
    python -m scripts.fiction_backtest run --run R --arm deepseek --part clean,famous --limit 10
    python -m scripts.fiction_backtest run --run R --arm deepseek --part clean,famous
    python -m scripts.fiction_backtest ingest --run R --arm file:opus --model-id claude-opus-...
    python -m scripts.fiction_backtest analyze --run R
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import exp_llm_blind_gap_2026_09_28 as X2          # noqa: E402

# ───────────────────────── constants ────────────────────────────────────────
RUN_ROOT = ROOT / "backend/data/optimus/fiction_backtest"
BARS = ROOT / "backend/data/optimus/prices_deep/bars.parquet"
BARS_DELISTED = ROOT / "backend/data/optimus/prices_deep/bars_delisted.parquet"
EIGHTK = ROOT / "backend/data/optimus/edgar_8k/eightk_items.parquet"
FACTS = ROOT / "backend/data/optimus/fundamentals_sec/sec_facts_history.parquet"
REVS = ROOT / "backend/data/optimus/analyst/target_revisions.parquet"
NEWS = ROOT / "backend/data/optimus/text_return_panel/news_returns_2025_26.parquet"
CRSP_PIT = ROOT / "backend/data/optimus/crsp_pit/crsp_pit_monthly_v1.parquet"
PANEL_V2 = ROOT / "backend/data/optimus/aegis_panel/aegis_panel_v2.parquet"
REGISTRATION = ROOT / "docs/TRIALS/TRIAL-AMNESIA-2-event-reaction-model-agnostic.md"
AMNESIA_SRC = Path("C:/Users/mrthn/Aegis module/aegis_brain/llm/amnesia.py")
AMNESIA_SHA256 = "ce07f68556149098eca01117079accea131de906f144ea91f2ab6d6b89beaf5d"

LEVELS = ("A0_NAMED", "A2_MASKED", "A3_SYNTHETIC")
FILE_ARM_LEVELS = ("A2_MASKED", "A3_SYNTHETIC")      # the clean part, for the file arm
CAP_USD = 2.00
FIRST_FLUSH = 10
PURPOSE = "fiction_backtest_amnesia2_2026_09_28"
SEED = 20260928
H_SHORT, H_LONG = 5, 21
HEADLINE_LOOKBACK_DAYS = 14
MAX_HEADLINES = 8
SNIPPETS = 3
SNIPPET_CHARS = 220
MIN_PRICE = 3.0
MIN_ADV = 5e6              # 63-session median dollar volume, sample filter
MEDIAN_UNIVERSE_MIN_DV = 1e6   # one-day dollar volume on t, for the median-stock benchmark
CLEAN_START, CLEAN_END = "2026-07-01", "2026-09-03"
BACKTEST_START, BACKTEST_END = "2018-01-01", "2025-06-30"
N_CLEAN, N_BACKTEST, N_FAMOUS = 600, 1200, 30
N_BACKTEST_BLOCKS = 20
ETFS = {"SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "RSP"}
CASE_ID_RE = re.compile(r"^[a-f0-9]{12}$")

#: Knowledge cutoffs, each with its source. A cutoff nobody can source is
#: measured with the X2 price probe (`X2.stage_probe`), never assumed.
ARM_CUTOFFS = {
    "deepseek": ("2025-12", "measured: X2 month-end price probe, "
                 "backend/data/optimus/experiments_2026-09-28/x2_blind_20260928_probe.json "
                 "(self-report says 'early 2025')"),
    "nvidia:meta/llama-3.2-11b-vision-instruct": ("2023-12", "Meta Llama 3.2 model card"),
    "local": ("2024-06", "Qwen2.5-7B receipts: community trackers, confidence MEDIUM"),
    "file:opus": ("2026-06", "stated by the orchestrator's model (Claude Opus 5.5 system "
                  "prompt: 'knowledge cutoff is June 2026'); unverified by probe"),
}

# ───────────────────────── vendored from amnesia.py (see header) ────────────
FAKE_PREFIX = ["Arden", "Belmar", "Corvin", "Dalmoor", "Elstree", "Fennick",
               "Garvey", "Halcyon", "Iverson", "Jandra", "Kestrel", "Lindow",
               "Marrow", "Norhaven", "Orrick", "Pellham", "Quarry", "Ridgeley",
               "Selwyn", "Tarnish", "Umbrey", "Vardon", "Wexler", "Yarrow"]
FAKE_SUFFIX = ["Industries", "Holdings", "Systems", "Group", "Works",
               "Partners", "Corporation", "Enterprises", "Technologies"]
SIM_HEADER = ("[SIMULATED SCENARIO — this company and date are fictional; "
              "no real-world facts about them exist]")


def fake_identity(key: str, real_tickers: frozenset = frozenset()) -> tuple:
    """amnesia.fake_identity's rule on an arbitrary key: (name, ticker, year).
    A fabricated ticker that spells a real one gets a trailing X (new)."""
    h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    name = f"{FAKE_PREFIX[h % len(FAKE_PREFIX)]} {FAKE_SUFFIX[(h // 7) % len(FAKE_SUFFIX)]}"
    ticker = (FAKE_PREFIX[h % len(FAKE_PREFIX)][:3] + chr(65 + h % 26)).upper()
    while ticker in real_tickers:
        ticker += "X"
    # amnesia.py: 2100 + (h % 40). +10 here (new): a date a year before the
    # anchor must not read as 20xx, or the leak scan refuses the case.
    year = 2100 + (h % 40) + 10
    return name, ticker, year


def parse_json_tolerant(text: str) -> dict:
    """amnesia.parse_json, verbatim logic: used for CANARY replies only."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        t = t[4:] if t.lower().startswith("json") else t
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < 0:
        raise ValueError(f"no JSON object in response: {text[:120]!r}")
    return json.loads(t[i:j + 1])


CANARY_SYSTEM = ("You answer only with strict JSON matching the requested schema. "
                 "Honesty about uncertainty is more valuable than a guess.")


def canary_user(level: str, case_text: str, *, company: str = "", ticker: str = "",
                date: str = "") -> str:
    """amnesia.canary_prompt's two wordings; horizon 12 months -> 5 sessions."""
    if level == "A0_NAMED":
        return (f"Company: {company} (ticker {ticker}). Date: {date}.\n\n"
                "Do you recall, from your training data, what happened to this "
                "company's stock over the 5 trading sessions following that date?\n"
                'Return JSON exactly: {"recall": "<YES|NO>", '
                '"direction": "<UP|DOWN|UNSURE>", "what": "<=25 words>"}')
    return ("The following describes a real US-listed company at some point in "
            "history, with its identity and date removed.\n\n"
            f"{case_text}\n\n"
            "Can you identify it?\n"
            'Return JSON exactly: {"company": "<name or UNKNOWN>", '
            '"ticker": "<ticker or UNKNOWN>", "year": <4-digit year or 0>, '
            '"confidence": "<HIGH|MEDIUM|LOW>"}')


# ───────────────────────── the question (new) ───────────────────────────────
FORECAST_SYSTEM = (
    "You are advising on one company. The case file describes its situation at the "
    "close of a decision session. Use only the case file; do not look anything up.\n\n"
    "1. Write three plausible ways the next 5 trading sessions could go (the company is "
    "expected to report quarterly results within them), each with a probability (the "
    "three sum to 1) and the range of the stock's total return, in percent, within that "
    "scenario.\n"
    "2. State the probability that the stock's return beats the median US stock's return "
    "over the next 5 sessions, and over the next 21 sessions.\n"
    "3. State your central estimate of the stock's 5-session return and an 80% range "
    "(10th to 90th percentile), in percent.\n"
    "4. Say in one sentence what would change your mind.\n"
    "5. Score the case file's text (headlines, events, analyst actions) on four 0-to-1 "
    "scales: novelty (0 nothing new, 1 genuinely new information); emotional_intensity "
    "(0 flat and factual, 1 fear or euphoria); management_confidence (0 evasive or "
    "defensive, 1 confident and specific, 0.5 if management is not heard from); "
    "crowdedness (0 nobody is paying attention, 1 everyone holds the same view).\n\n"
    "Reply with ONLY one JSON object, no prose before or after it, with exactly these keys:\n"
    '{"scenarios": [{"label": "<short>", "prob": <0-1>, "ret_low_pct": <number>, '
    '"ret_high_pct": <number>}, {...}, {...}], '
    '"p_beat_median_5d": <0-1>, "p_beat_median_21d": <0-1>, '
    '"central_5d_pct": <number>, "low80_5d_pct": <number>, "high80_5d_pct": <number>, '
    '"change_mind": "<one sentence>", '
    '"features": {"novelty": <0-1>, "emotional_intensity": <0-1>, '
    '"management_confidence": <0-1>, "crowdedness": <0-1>}}'
)
FEATURES = ("novelty", "emotional_intensity", "management_confidence", "crowdedness")
_FENCE = re.compile(r"^\s*(?:```(?:json)?\s*)?(\{.*\})\s*(?:```)?\s*$", re.S)


def _num(x: Any) -> Optional[float]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def parse_forecast(text: Optional[str]) -> tuple:
    """STRICT. -> (parsed dict, None) or (None, refusal_reason). Never repairs:
    the reply must be exactly one JSON object (a ```json fence is tolerated,
    any other text is not) and every field must be present and valid."""
    if not text or not text.strip():
        return None, "EMPTY"
    m = _FENCE.match(text)
    if not m:
        return None, "NOT_A_SINGLE_JSON_OBJECT"
    try:
        o = json.loads(m.group(1))
    except ValueError:
        return None, "JSON_DECODE"
    if not isinstance(o, dict):
        return None, "NOT_AN_OBJECT"
    sc = o.get("scenarios")
    if not isinstance(sc, list) or len(sc) != 3:
        return None, "SCENARIOS_NOT_THREE"
    scen = []
    for s in sc:
        if not isinstance(s, dict):
            return None, "SCENARIO_NOT_OBJECT"
        p, lo, hi = _num(s.get("prob")), _num(s.get("ret_low_pct")), _num(s.get("ret_high_pct"))
        if p is None or lo is None or hi is None or not (0 <= p <= 1) or not (lo <= hi):
            return None, "SCENARIO_FIELDS"
        if abs(lo) > 500 or abs(hi) > 500:
            return None, "SCENARIO_RANGE_ABSURD"
        scen.append({"label": str(s.get("label", ""))[:80], "prob": p,
                     "ret_low_pct": lo, "ret_high_pct": hi})
    if abs(sum(s["prob"] for s in scen) - 1.0) > 0.02:
        return None, "PROBS_DO_NOT_SUM_TO_1"
    out: dict = {"scenarios": scen}
    for k in ("p_beat_median_5d", "p_beat_median_21d"):
        v = _num(o.get(k))
        if v is None or not (0 <= v <= 1):
            return None, f"BAD_{k.upper()}"
        out[k] = v
    c, lo, hi = (_num(o.get("central_5d_pct")), _num(o.get("low80_5d_pct")),
                 _num(o.get("high80_5d_pct")))
    if c is None or lo is None or hi is None or not (lo < hi) or not (lo <= c <= hi):
        return None, "BAD_CENTRAL_OR_RANGE"
    if abs(lo) > 500 or abs(hi) > 500:
        return None, "RANGE_ABSURD"
    out.update(central_5d_pct=c, low80_5d_pct=lo, high80_5d_pct=hi)
    cm = o.get("change_mind")
    if not isinstance(cm, str) or not cm.strip():
        return None, "NO_CHANGE_MIND"
    out["change_mind"] = cm.strip()[:600]
    f = o.get("features")
    if not isinstance(f, dict):
        return None, "NO_FEATURES"
    feats = {}
    for k in FEATURES:
        v = _num(f.get(k))
        if v is None or not (0 <= v <= 1):
            return None, f"BAD_FEATURE_{k.upper()}"
        feats[k] = v
    out["features"] = feats
    return out, None


def parse_canary(level: str, text: Optional[str]) -> tuple:
    try:
        o = parse_json_tolerant(text or "")
    except (ValueError, TypeError):
        return None, "CANARY_UNPARSEABLE"
    if not isinstance(o, dict):
        return None, "CANARY_UNPARSEABLE"
    if level == "A0_NAMED":
        r = str(o.get("recall", "")).upper()
        d = str(o.get("direction", "")).upper()
        if r not in ("YES", "NO"):
            return None, "CANARY_SCHEMA"
        return {"recall": r, "direction": d if d in ("UP", "DOWN", "UNSURE") else "UNSURE",
                "what": str(o.get("what", ""))[:200]}, None
    y = o.get("year")
    try:
        y = int(y) if y not in (None, "") else 0
    except (TypeError, ValueError):
        y = 0
    return {"company": str(o.get("company", "UNKNOWN"))[:120],
            "ticker": str(o.get("ticker", "UNKNOWN"))[:12].upper(), "year": y,
            "confidence": str(o.get("confidence", ""))[:10].upper()}, None


# ───────────────────────── PIT packet (new; X2 helpers reused) ──────────────
def et_cut(t) -> pd.Timestamp:
    """00:00 America/New_York on the decision date, in UTC. Every dated text
    item must be strictly before it: nothing dated ON the decision date."""
    return pd.Timestamp(pd.Timestamp(t).date()).tz_localize("America/New_York").tz_convert("UTC")


def _pct(a: float, b: float) -> float:
    return float((a / b - 1) * 100) if (b and np.isfinite(a) and np.isfinite(b)) else float("nan")


def price_block(closes: np.ndarray, volumes: np.ndarray) -> dict:
    """X2.price_summary (levels-free) + the levels the fiction layer rescales."""
    c = np.asarray(closes, float)
    v = np.asarray(volumes, float)
    s = X2.price_summary(c, v)
    s["ret_126d_pct"] = _pct(c[-1], c[-127]) if len(c) > 126 else float("nan")
    w = c[-252:]
    hi, lo = float(np.max(w)), float(np.min(w))
    s["range_position_52w_pct"] = float((c[-1] - lo) / (hi - lo) * 100) if hi > lo else 50.0
    s["mom_12_1_pct"] = _pct(c[-22], c[-253]) if len(c) > 252 else float("nan")
    return {"summary": s, "last_close": float(c[-1]), "high_52w": hi, "low_52w": lo,
            "adv63_usd": float(np.median((c * v)[-63:]))}


def past_reactions(bars_dates: np.ndarray, closes: np.ndarray, event_dates: list, t,
                   h: int = H_SHORT, k: int = 4) -> list:
    """5-session returns from the session before each PRIOR earnings filing,
    only where the whole window closed strictly before t. -> [(date, pct)]."""
    out = []
    tt = np.datetime64(pd.Timestamp(t))
    for d in sorted(event_dates):
        dd = np.datetime64(pd.Timestamp(d))
        i = int(np.searchsorted(bars_dates, dd, side="left")) - 1   # session before filing
        if i < 0 or i + h >= len(closes) or bars_dates[i + h] >= tt:
            continue
        out.append((str(pd.Timestamp(bars_dates[i]).date()), _pct(closes[i + h], closes[i])))
    return out[-k:]


def fundamentals_block(f: Optional[pd.DataFrame], t) -> Optional[dict]:
    """Latest facts FILED strictly before t. Quarterly flows (80-100 day periods)."""
    if f is None or f.empty:
        return None
    f = f[f["filed"] < pd.Timestamp(pd.Timestamp(t).date())]
    if f.empty:
        return None
    out: dict = {"filed": str(pd.Timestamp(f["filed"].max()).date())}
    q = f[(f["period_days"] >= 80) & (f["period_days"] <= 100)]
    for fact in ("revenue", "operating_income", "net_income"):
        g = q[q["fact"] == fact].sort_values(["end", "filed"]).drop_duplicates("end", keep="last")
        if g.empty:
            continue
        out[f"{fact}_q"] = float(g["val"].iloc[-1])
        if fact == "revenue":
            e = pd.Timestamp(g["end"].iloc[-1])
            ya = g[(pd.to_datetime(g["end"]) - (e - pd.Timedelta(days=365))).abs() <= pd.Timedelta(days=20)]
            if len(ya) and ya["val"].iloc[-1]:
                out["revenue_yoy_pct"] = _pct(float(g["val"].iloc[-1]), float(ya["val"].iloc[-1]))
            if len(g) >= 4:
                out["revenue_ttm"] = float(g["val"].iloc[-4:].sum())
    for fact in ("assets", "cash", "debt", "equity", "shares"):
        g = f[f["fact"] == fact].sort_values(["end", "filed"])
        if len(g):
            out[fact] = float(g["val"].iloc[-1])
    if out.get("revenue_q") and out.get("operating_income_q") is not None:
        out["op_margin_pct"] = out["operating_income_q"] / out["revenue_q"] * 100
    if out.get("revenue_q") and out.get("net_income_q") is not None:
        out["net_margin_pct"] = out["net_income_q"] / out["revenue_q"] * 100
    return out


def split_factor(shares_at_t: Optional[float], shares_latest: Optional[float]) -> float:
    """Bars are split-adjusted to TODAY; filed share counts and analyst targets
    are as of their own date. A share-count ratio far from 1 is a split (a
    buyback moves it a few percent): round it to the split and return it.
    Targets are divided by it and share counts multiplied, so every level in the
    packet sits on the same (today's) share basis."""
    if not shares_at_t or not shares_latest or shares_at_t <= 0:
        return 1.0
    r = shares_latest / shares_at_t
    if r >= 1.8:
        return float(round(r))
    if r <= 0.55:
        return 1.0 / round(1.0 / r)
    return 1.0


def analyst_block(r: Optional[pd.DataFrame], t, last_close: float,
                  split: float = 1.0) -> Optional[dict]:
    if r is None or r.empty:
        return None
    r = r[r["event_date"] < pd.Timestamp(pd.Timestamp(t).date())]
    if r.empty:
        return None
    r = r.sort_values("event_date")
    w = r[r["event_date"] >= pd.Timestamp(t) - pd.Timedelta(days=90)]
    tgt = w["current_target"].dropna() / split
    acts = []
    for _, x in r.tail(5).iterrows():
        acts.append({"date": str(pd.Timestamp(x["event_date"]).date()), "firm": str(x["firm"]),
                     "action": str(x["action"]), "from": str(x["from_grade"] or ""),
                     "to": str(x["to_grade"] or ""),
                     "target_change_pct": (float(x["target_change"]) * 100
                                           if pd.notna(x["target_change"]) else None),
                     "target": (float(x["current_target"]) / split
                                if pd.notna(x["current_target"]) else None)})
    return {"n_90d": int(len(w)), "upgrades_90d": int((w["action"] == "up").sum()),
            "downgrades_90d": int((w["action"] == "down").sum()),
            "target_raises_90d": int((w["target_action"] == "Raises").sum()),
            "target_cuts_90d": int((w["target_action"] == "Lowers").sum()),
            "median_target_vs_price_pct": (_pct(float(tgt.median()), last_close) if len(tgt) else None),
            "actions": acts}


def headlines_pit(n: Optional[pd.DataFrame], t) -> list:
    """Headlines published strictly before 00:00 ET of the decision date, within
    the lookback, newest first, deduplicated; the first SNIPPETS carry a snippet."""
    if n is None or n.empty:
        return []
    cut = et_cut(t)
    n = n[(n["pub"] < cut) & (n["pub"] >= cut - pd.Timedelta(days=HEADLINE_LOOKBACK_DAYS))]
    n = n.sort_values("pub", ascending=False).drop_duplicates("title").head(MAX_HEADLINES)
    out = []
    for j, (p_, ti, bo) in enumerate(zip(n["pub"], n["title"], n["body"])):
        sn = re.sub(r"\s+", " ", str(bo or ""))[:SNIPPET_CHARS] if j < SNIPPETS else ""
        out.append({"date": str(p_.tz_convert("America/New_York").date()), "title": str(ti),
                    "snippet": sn})
    return out


def events_pit(e: Optional[pd.DataFrame], t) -> list:
    if e is None or e.empty:
        return []
    cut = et_cut(t)
    e = e[(e["pub"] < cut) & (e["pub"] >= cut - pd.Timedelta(days=HEADLINE_LOOKBACK_DAYS))]
    e = e.sort_values("pub")
    return [{"date": str(p_.tz_convert("America/New_York").date()), "event_type": str(et),
             "direction": str(dr)} for p_, et, dr in zip(e["pub"], e["event_type"], e["direction"])][-3:]


def assert_pit(packet: dict) -> list:
    """Every dated item strictly before the decision date. -> violations."""
    t = packet["decision_date"]
    bad = []
    for sec in ("headlines", "events"):
        for it in packet.get(sec) or []:
            if it["date"] >= t:
                bad.append((sec, it["date"]))
    for it in (packet.get("analyst") or {}).get("actions", []):
        if it["date"] >= t:
            bad.append(("analyst", it["date"]))
    f = packet.get("fundamentals") or {}
    if f.get("filed") and f["filed"] >= t:
        bad.append(("fundamentals", f["filed"]))
    for d, _ in packet.get("past_reactions") or []:
        if d >= t:
            bad.append(("past_reactions", d))
    return bad


# ───────────────────────── rendering + the fiction transform ─────────────────
_MONTH_WORDS = ("January February March April May June July August September October "
                "November December").split()
_YEAR_RE = re.compile(r"(?<![\d$.,])((?:19|20)\d{2})(?![\d%])")
_TICKER_REF = re.compile(r"\$[A-Z]{1,5}\b|\((?:(?:NASDAQ|NYSE|AMEX|NYSEARCA|OTC|CBOE)\s*:\s*)?[A-Z]{1,5}\)")
_MONEY_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)(\s?(?:billion|million|trillion|bn|mn|[BMT])\b)?")


def case_mapping(case_key: str, level: str, real_tickers: frozenset, rng_seed: int) -> dict:
    """Everything needed to render (and to unblind) one case at one level."""
    m: dict = {"level": level}
    if level == "A2_MASKED":
        rng = np.random.default_rng(rng_seed + 1)
        m.update(k_price=None,        # set per packet: 100 / last close (the rebasing)
                 k_size=float(np.exp(rng.uniform(np.log(0.2), np.log(5.0)))))
    if level == "A3_SYNTHETIC":
        name, tic, year = fake_identity(case_key, real_tickers)
        rng = np.random.default_rng(rng_seed)
        m.update(fake_name=name, fake_ticker=tic, fake_year=int(year),
                 k_price=float(np.exp(rng.uniform(np.log(0.2), np.log(5.0)))),
                 k_size=float(np.exp(rng.uniform(np.log(0.2), np.log(5.0)))))
    return m


def fmt_date(d: str, level: str, t: str, m: dict) -> str:
    if level == "A0_NAMED":
        return d
    if level == "A2_MASKED":
        n = (pd.Timestamp(t) - pd.Timestamp(d)).days
        return f"day -{n}" if n else "day 0"
    ts = pd.Timestamp(d)
    y = m["fake_year"] + (ts.year - pd.Timestamp(t).year)
    return f"{ts.day} {_MONTH_WORDS[ts.month - 1][:3]} {y}"


def unfmt_date(s: str, level: str, t: str, m: dict) -> str:
    """The inverse of fmt_date (the mapping round-trips)."""
    if level == "A0_NAMED":
        return s
    if level == "A2_MASKED":
        n = 0 if s == "day 0" else int(s.split("-")[1])
        return str((pd.Timestamp(t) - pd.Timedelta(days=n)).date())
    day, mon, y = s.split()
    real_y = int(y) - m["fake_year"] + pd.Timestamp(t).year
    return str(pd.Timestamp(f"{real_y}-{[w[:3] for w in _MONTH_WORDS].index(mon) + 1:02d}-{int(day):02d}").date())


def scale_money(v: float, kind: str, m: dict, inverse: bool = False) -> float:
    k = m["k_price"] if kind == "price" else m["k_size"]
    return v / k if inverse else v * k


def fiction_text(text: str, level: str, aliases: list, m: dict, t: str) -> str:
    """Subject -> code (X2.blind_text), explicit ticker references removed,
    years removed (A2) or shifted by the case's constant (A3), dollar amounts
    rescaled by the case's factors (A3; amounts with a size unit by k_size,
    bare amounts by k_price). Everything else is left as written: the canary,
    not this function, is what shows whether the text leaks."""
    if level == "A0_NAMED" or not text:
        return text
    code = "the company" if level == "A2_MASKED" else m["fake_name"]
    out = _TICKER_REF.sub("", text)            # before the name is coded, or "(NYSE: X)" survives
    out = X2.blind_text(out, aliases, code)
    if level == "A2_MASKED":
        out = _YEAR_RE.sub("", out)
    else:
        dy = m["fake_year"] - pd.Timestamp(t).year
        out = _YEAR_RE.sub(lambda g: str(int(g.group(1)) + dy), out)

    def money(g):
        num = float(g.group(1).replace(",", ""))
        unit = g.group(2) or ""
        v = scale_money(num, "size" if unit.strip() else "price", m)
        return f"${v:,.2f}{unit}"
    out = _MONEY_RE.sub(money, out)
    return re.sub(r"\s{2,}", " ", out).strip()


def _money(v: Optional[float], kind: str, level: str, m: dict) -> str:
    if v is None or not np.isfinite(v):
        return "n/a"
    if level == "A3_SYNTHETIC":
        v = scale_money(v, kind, m)
    if kind == "price":
        return f"${v:,.2f}"
    a = abs(v)
    for div, u in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= div:
            return f"${v / div:,.2f}{u}"
    return f"${v:,.0f}"


_ACTIONS = {"main": "maintained", "init": "initiated", "up": "upgraded", "down": "downgraded",
            "reit": "reiterated"}

_SUMMARY_NAMES = {"ret_1d_pct": "return 1d", "ret_5d_pct": "5d", "ret_21d_pct": "21d",
                  "ret_63d_pct": "63d", "ret_126d_pct": "126d", "ret_252d_pct": "252d",
                  "mom_12_1_pct": "12-1 momentum", "vol_21d_daily_pct": "daily vol 21d",
                  "vol_63d_daily_pct": "daily vol 63d", "pct_below_52w_high": "below 52w high",
                  "range_position_52w_pct": "position in 52w range",
                  "volume_5d_vs_63d": "volume 5d/63d (x)"}


def render_case(packet: dict, level: str, m: dict, aliases: list, case_id: str) -> tuple:
    """-> (text, n_dropped_headlines). A2 carries NO absolute money amount
    (leakage_probe.mask_snapshot's rebasing: last close = 100); A3 carries them
    rescaled; A0 carries them as they were. Percentages and ratios are the same
    numbers at every level."""
    t = packet["decision_date"]
    p = packet["price"]
    s = p["summary"]
    L = []
    if level == "A3_SYNTHETIC":
        L.append(SIM_HEADER)
    L.append(f"CASE {case_id}")
    if level == "A0_NAMED":
        L.append(f"Company: {packet['company']} (ticker {packet['symbol']}). "
                 f"Decision date: {t}, at the close.")
    elif level == "A2_MASKED":
        L.append("A US-listed company, identity withheld. The date is withheld: the decision "
                 "session is 'day 0' and other dates are given as calendar days before it.")
    else:
        L.append(f"Company: {m['fake_name']} (ticker {m['fake_ticker']}). "
                 f"Simulation date: {fmt_date(t, level, t, m)}, at the close.")
    L.append(f"Sector: {packet['sector']}. Size: {packet['size_bucket']}.")
    L.append("The company is expected to report quarterly results within the next two sessions.")
    L.append("")
    L.append("PRICE AND VOLUME (to the decision close)")
    if level == "A2_MASKED":
        k = 100.0 / p["last_close"]
        L.append(f"  last close rebased to 100.00; 52-week high {p['high_52w'] * k:.2f}, "
                 f"low {p['low_52w'] * k:.2f}")
    else:
        L.append(f"  last close {_money(p['last_close'], 'price', level, m)}; 52-week high "
                 f"{_money(p['high_52w'], 'price', level, m)}, low {_money(p['low_52w'], 'price', level, m)}; "
                 f"median daily dollar volume {_money(p['adv63_usd'], 'size', level, m)}")
    L.append("  " + "; ".join(f"{_SUMMARY_NAMES[k2]} {v:.2f}{'' if k2 == 'volume_5d_vs_63d' else '%'}"
                              for k2, v in s.items() if k2 in _SUMMARY_NAMES and np.isfinite(v)))
    pr = packet.get("past_reactions") or []
    if pr:
        L.append("  5-session reactions to the previous earnings reports: " +
                 "; ".join(f"{fmt_date(d, level, t, m)}: {v:+.1f}%" for d, v in pr))
    f = packet.get("fundamentals")
    L.append("")
    L.append("FUNDAMENTALS (as filed)")
    if f:
        L.append(f"  latest filing {fmt_date(f['filed'], level, t, m)}")
        parts = []
        for key, lab in (("revenue_yoy_pct", "quarterly revenue growth y/y"),
                         ("op_margin_pct", "operating margin"), ("net_margin_pct", "net margin")):
            if f.get(key) is not None and np.isfinite(f[key]):
                parts.append(f"{lab} {f[key]:.1f}%")
        mcap = (p["last_close"] * f["shares"]) if f.get("shares") else None
        if mcap and f.get("revenue_ttm"):
            parts.append(f"market value / trailing revenue {mcap / f['revenue_ttm']:.2f}x")
        if f.get("assets") and f.get("cash") is not None:
            parts.append(f"cash / assets {f['cash'] / f['assets'] * 100:.1f}%")
        if f.get("equity") and f.get("debt") is not None and f["equity"] > 0:
            parts.append(f"debt / equity {f['debt'] / f['equity']:.2f}x")
        L.append("  " + ("; ".join(parts) if parts else "ratios unavailable"))
        if level != "A2_MASKED":
            lv = [x for x in (
                f"quarterly revenue {_money(f.get('revenue_q'), 'size', level, m)}" if f.get("revenue_q") else "",
                f"quarterly net income {_money(f.get('net_income_q'), 'size', level, m)}"
                if f.get("net_income_q") is not None else "",
                f"market value {_money(mcap, 'size', level, m)}" if mcap else "") if x]
            if lv:
                L.append("  " + "; ".join(lv))
    else:
        L.append("  none on file")
    a = packet.get("analyst")
    L.append("")
    L.append("ANALYST ACTIONS (dated before the decision date)")
    if a:
        L.append(f"  last 90 days: {a['n_90d']} actions, {a['upgrades_90d']} upgrades, "
                 f"{a['downgrades_90d']} downgrades, {a['target_raises_90d']} objective raises, "
                 f"{a['target_cuts_90d']} objective cuts")
        # objective LEVELS are not shown at any level: bars are split-adjusted to
        # today, targets are as of their date, and the share-count split
        # heuristic is not reliable enough to put a level beside a price
        firms: dict = {}
        for x in a["actions"]:
            firm = x["firm"] if level == "A0_NAMED" else firms.setdefault(x["firm"], f"Broker {len(firms) + 1}")
            tc = f", objective {x['target_change_pct']:+.1f}%" if x["target_change_pct"] is not None else ""
            lvl = ""
            act = _ACTIONS.get(x["action"], x["action"])
            L.append(f"  {fmt_date(x['date'], level, t, m)}: {firm} {act} "
                     f"{x['from']}->{x['to']}{tc}{lvl}")
    else:
        L.append("  none on file")
    L.append("")
    L.append("TYPED EVENTS")
    ev = packet.get("events") or []
    L += [f"  {fmt_date(e['date'], level, t, m)}: {e['event_type']} ({e['direction']})" for e in ev] \
        or ["  none on file"]
    L.append("")
    L.append("HEADLINES (published before the decision date)")
    dropped = 0
    hl = []
    for h in packet.get("headlines") or []:
        title = fiction_text(h["title"], level, aliases, m, t)
        snip = fiction_text(h.get("snippet") or "", level, aliases, m, t)
        line = f"  {fmt_date(h['date'], level, t, m)}: {title}" + (f" | {snip}" if snip else "")
        if level != "A0_NAMED" and X2.leaks(line, aliases):
            dropped += 1          # an item that still names the company is refused, not repaired
            continue
        hl.append(line)
    L += hl or ["  none on file"]
    return "\n".join(L), dropped


def scan_case(text: str, level: str, packet: dict, aliases: list) -> list:
    """leakage_probe.masking_violations (A2/A3) + X2.leaks on every alias.
    A non-empty list REFUSES the case at that level (never repaired)."""
    if level == "A0_NAMED":
        return []
    from backend.services.leakage_probe import masking_violations      # noqa: PLC0415
    v = masking_violations(text, ticker=packet["symbol"], company_name=packet["company"] or "",
                           as_of=packet["decision_date"], last_close=packet["price"]["last_close"],
                           benchmark="")
    v += [{"kind": "alias", "match": a} for a in X2.leaks(text, aliases)]
    return v


def case_file_text(kind: str, body: str) -> str:
    """What a FILE-arm answering agent sees: the question and the case, nothing else."""
    if kind == "forecast":
        return ("QUESTION\n" + FORECAST_SYSTEM + "\n\n" + body + "\n\nWrite the JSON answer for "
                "this case into the answer file named after this case.\n")
    return "QUESTION\n" + CANARY_SYSTEM + "\n\n" + body + "\n"


# ───────────────────────── budget (the cap) ─────────────────────────────────
class CapRefused(RuntimeError):
    """The run's dollar cap would be exceeded, or spend cannot be priced."""


class Budget:
    """Thread-safe dollar cap over the WHOLE run (every arm, every stage):
    prior spend is read from the run's call ledger, every call reserves an
    estimate first, and an unpriced successful call makes the cap refuse
    everything after it (a cap that cannot price cannot bind)."""

    def __init__(self, cap: float, ledger: Optional[Path]):
        self.cap, self.ledger = float(cap), ledger
        self.lock = threading.Lock()
        self.spent, self.reserved, self.unknown, self.max_seen = 0.0, 0.0, False, 0.0
        if ledger is not None and ledger.exists():
            for ln in ledger.read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                c = json.loads(ln)
                if c.get("ok") and c.get("cost_usd") is None:
                    self.unknown = True
                self.spent += c.get("cost_usd") or 0.0
                self.max_seen = max(self.max_seen, c.get("cost_usd") or 0.0)

    def est(self) -> float:
        return max(2 * self.max_seen, 0.002)

    def reserve(self) -> float:
        with self.lock:
            e = self.est()
            if self.unknown:
                raise CapRefused("an earlier call could not be priced")
            if self.spent + self.reserved + e > self.cap:
                raise CapRefused(f"spent {self.spent:.4f} + in flight {self.reserved:.4f} + "
                                 f"next ~{e:.4f} > cap {self.cap:.2f}")
            self.reserved += e
            return e

    def settle(self, reserved: float, rec: dict) -> None:
        with self.lock:
            self.reserved -= reserved
            c = rec.get("cost_usd")
            if rec.get("ok") and c is None:
                self.unknown = True
            self.spent += c or 0.0
            self.max_seen = max(self.max_seen, c or 0.0)
            if self.ledger is not None:
                with open(self.ledger, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")


# ───────────────────────── arms ─────────────────────────────────────────────
class Arm:
    """answer(system, user, case_id) -> {text, served_model, cost_usd, status, ok, error}."""
    name = "abstract"
    model_id: Optional[str] = None
    paid = False

    def answer(self, system: str, user: str, case_id: str) -> dict:   # pragma: no cover
        raise NotImplementedError


class DeepSeekArm(Arm):
    """The project's provider through its one route (`call_named`), with this
    run's own dollar cap (`production_budget=False`: the 150-call counter is
    sized for an endpoint; the billing breaker still binds)."""
    name, model_id, paid = "deepseek", "deepseek-chat", True

    def answer(self, system, user, case_id):
        from backend.services import llm_analyzer as LA                # noqa: PLC0415
        r = LA.call_named("deepseek", system, user, purpose=PURPOSE, max_tokens=900,
                          production_budget=False)
        return {"text": r.get("text"), "served_model": r.get("served_model"),
                "cost_usd": r.get("cost_usd"), "status": r.get("status"), "ok": bool(r.get("ok")),
                "error": r.get("error"), "tokens_in": r.get("tokens_in"),
                "tokens_out": r.get("tokens_out")}


class NvidiaArm(Arm):
    """NIM free tier, any model with a $0 row in LLM_PRICE_PER_MTOK (an unlisted
    model refuses: unpriced is not free). Reuses llm_analyzer's client, 429
    retry, content-only reply rule and telemetry."""
    paid = False

    def __init__(self, model: str):
        self.model_id = model
        self.name = f"nvidia:{model}"

    def answer(self, system, user, case_id):
        from backend import config as C                                 # noqa: PLC0415
        from backend.services import llm_analyzer as LA                 # noqa: PLC0415
        from backend.services import llm_telemetry as TEL               # noqa: PLC0415
        if self.model_id not in C.LLM_PRICE_PER_MTOK:
            return {"text": None, "ok": False, "status": "UNPRICED_MODEL", "cost_usd": None,
                    "served_model": None, "error": "no price row"}
        client = LA._get_nvidia_client()
        if client is None:
            return {"text": None, "ok": False, "status": "NOT_CONFIGURED", "cost_usd": 0.0,
                    "served_model": None, "error": "NVIDIA_API_KEY is not set"}
        t0 = time.perf_counter()
        kw = dict(model=self.model_id, max_tokens=900, temperature=0.3,
                  messages=[{"role": "system", "content": system + LA._LANGUAGE_PIN},
                            {"role": "user", "content": user}])
        try:
            resp, _ = LA._create_with_429_retry(client, "nvidia", **kw)
            text = LA._reply_text(resp)
        except Exception as e:                                          # noqa: BLE001
            LA._record("nvidia", self.model_id, PURPOSE, system=system, user=user, t0=t0, error=e)
            return {"text": None, "ok": False, "status": "ERROR", "cost_usd": 0.0,
                    "served_model": None, "error": f"{type(e).__name__}: {str(e)[:200]}"}
        LA._record("nvidia", self.model_id, PURPOSE, system=system, user=user, resp=resp,
                   text=text, t0=t0)
        u = TEL.extract_usage(resp, "nvidia")
        served = getattr(resp, "model", None) or self.model_id
        return {"text": text or None, "ok": bool(text), "status": "OK" if text else "EMPTY",
                "served_model": served, "error": None,
                "cost_usd": TEL.price_call(self.model_id, u.get("tokens_in", 0),
                                           u.get("tokens_out", 0), u.get("cached_tokens", 0)),
                "tokens_in": u.get("tokens_in"), "tokens_out": u.get("tokens_out")}


class LocalArm(Arm):
    """The local llama-server, ONLY if it is already up and the operator allowed
    it. It never starts a server (`llama_server.ensure` is not called)."""
    name, model_id, paid = "local", "local", False

    def __init__(self, allowed: bool = False):
        self.allowed = allowed

    def up(self) -> bool:
        from backend.services import llama_server as LS                 # noqa: PLC0415
        try:
            with socket.create_connection((LS.LLAMA_HOST, int(LS.LLAMA_PORT)), timeout=1.0):
                return True
        except OSError:
            return False

    def answer(self, system, user, case_id):
        if not self.allowed or not self.up():
            return {"text": None, "ok": False, "status": "LOCAL_UNAVAILABLE", "cost_usd": 0.0,
                    "served_model": None, "error": "not allowed or no server up; never started here"}
        from backend.services import llm_analyzer as LA                 # noqa: PLC0415
        client = LA._get_local_client()
        resp = client.chat.completions.create(model="local", max_tokens=900, temperature=0.3,
                                              messages=[{"role": "system", "content": system},
                                                        {"role": "user", "content": user}])
        text = LA._reply_text(resp)
        return {"text": text or None, "ok": bool(text), "status": "OK" if text else "EMPTY",
                "served_model": getattr(resp, "model", "local"), "cost_usd": 0.0, "error": None}


class FileArm(Arm):
    """Reads `<run>/answers/<name>/<case_id>.txt` and nothing else. The case id
    must match the harness's own id shape and the resolved path must sit inside
    the answers folder, so a crafted id cannot walk out of it."""
    paid = False

    def __init__(self, run_dir: Path, name: str, model_id: Optional[str] = None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", name) or name in (".", ".."):
            raise ValueError(f"bad file-arm name {name!r}")
        self.name = f"file:{name}"
        self.model_id = model_id
        self.dir = (run_dir / "answers" / name).resolve()

    def path_for(self, case_id: str) -> Path:
        if not CASE_ID_RE.fullmatch(case_id or ""):
            raise ValueError(f"refused case id {case_id!r}")
        p = (self.dir / f"{case_id}.txt").resolve()
        if p.parent != self.dir:
            raise ValueError(f"refused path outside the answers folder: {p}")
        return p

    def answer(self, system, user, case_id):
        p = self.path_for(case_id)
        if not p.is_file():
            return {"text": None, "ok": False, "status": "NO_ANSWER_FILE", "cost_usd": 0.0,
                    "served_model": self.model_id, "error": None}
        return {"text": p.read_text(encoding="utf-8", errors="replace"), "ok": True,
                "status": "OK", "cost_usd": 0.0, "served_model": self.model_id, "error": None}


def make_arm(spec: str, run_dir: Path, model_id: Optional[str] = None,
             allow_local: bool = False) -> Arm:
    if spec == "deepseek":
        return DeepSeekArm()
    if spec.startswith("nvidia"):
        from backend import config as C                                 # noqa: PLC0415
        return NvidiaArm(spec.split(":", 1)[1] if ":" in spec else C.NVIDIA_ADJUDICATOR_MODEL)
    if spec == "local":
        return LocalArm(allow_local)
    if spec.startswith("file:"):
        return FileArm(run_dir, spec.split(":", 1)[1], model_id)
    raise ValueError(f"unknown arm {spec!r}")


# ───────────────────────── data loading ─────────────────────────────────────
def load_bars(start: str, symbols=None) -> pd.DataFrame:
    """prices_deep bars + the delisted names' bars (survivorship: a name that
    stopped trading stays in the sample)."""
    cols = ["symbol", "date", "close", "volume"]
    f = [("date", ">=", pd.Timestamp(start))]
    if symbols is not None:
        f.append(("symbol", "in", sorted(symbols)))
    a = pd.read_parquet(BARS, columns=cols, filters=f)
    b = pd.read_parquet(BARS_DELISTED, columns=cols, filters=f)
    live = set(a["symbol"].unique())
    b = b[~b["symbol"].isin(live)]
    d = pd.concat([a, b], ignore_index=True)
    d["delisted_file"] = ~d["symbol"].isin(live)
    return d.sort_values(["symbol", "date"]).reset_index(drop=True)


def load_events() -> pd.DataFrame:
    d = pd.read_parquet(EIGHTK, columns=["ticker", "filing_date", "items_joined"])
    d = d[d["items_joined"].fillna("").str.contains(r"\b2\.02\b", regex=True)]
    d["filing_date"] = pd.to_datetime(d["filing_date"], errors="coerce")
    d = d.dropna(subset=["filing_date", "ticker"])
    d["ticker"] = d["ticker"].astype(str).str.upper()
    return d.drop_duplicates(["ticker", "filing_date"])


_GICS = {"10": "energy", "15": "materials", "20": "industrials", "25": "consumer discretionary",
         "30": "consumer staples", "35": "health care", "40": "financials",
         "45": "information technology", "50": "communication services", "55": "utilities",
         "60": "real estate"}


def load_names_sectors() -> tuple:
    """ticker -> SEC title; ticker -> CRSP comnam; ticker -> coarse GICS sector
    (CRSP permno's latest ticker joined to the panel's latest gics)."""
    titles = X2.load_titles()
    cp = pd.read_parquet(CRSP_PIT, columns=["permno", "date", "ticker", "comnam"])
    cp = cp.dropna(subset=["ticker"]).sort_values("date").drop_duplicates("ticker", keep="last")
    comnam = dict(zip(cp["ticker"].astype(str).str.upper(), cp["comnam"].astype(str)))
    pan = pd.read_parquet(PANEL_V2, columns=["permno", "eom", "gics"]).dropna(subset=["gics"])
    pan = pan.sort_values("eom").drop_duplicates("permno", keep="last")
    g = dict(zip(pd.to_numeric(pan["permno"], errors="coerce").astype("Int64"),
                 pan["gics"].astype("int64").astype(str).str[:2]))
    sector = {}
    for tk, pn in zip(cp["ticker"].astype(str).str.upper(), cp["permno"]):
        try:
            s = _GICS.get(g.get(int(pn), ""), None)
        except (TypeError, ValueError):
            s = None
        if s:
            sector[tk] = s
    return titles, comnam, sector


def size_bucket(mcap: Optional[float], adv: float) -> str:
    if mcap:
        for lim, lab in ((200e9, "mega cap"), (10e9, "large cap"), (2e9, "mid cap"), (3e8, "small cap")):
            if mcap >= lim:
                return lab
        return "micro cap"
    for lim, lab in ((1e9, "mega-cap liquidity"), (1e8, "large-cap liquidity"),
                     (2e7, "mid-cap liquidity")):
        if adv >= lim:
            return lab
    return "small-cap liquidity"


def aliases_for(sym: str, titles: dict, comnam: dict) -> list:
    al = X2.name_aliases(sym, titles.get(sym))
    if comnam.get(sym):
        al += [a for a in X2.name_aliases(sym, comnam[sym].title()) if a not in al]
    seen, out = set(), []
    for a in sorted(al, key=len, reverse=True):
        if a.upper() not in seen:
            seen.add(a.upper())
            out.append(a)
    return out


# ───────────────────────── sampling ─────────────────────────────────────────
def decision_session(dates: np.ndarray, filing: pd.Timestamp) -> Optional[int]:
    """The last session strictly before the filing date: the 5-session window
    then contains the reaction whether the release came before or after the bell."""
    i = int(np.searchsorted(dates, np.datetime64(filing), side="left")) - 1
    return i if i >= 0 else None


def candidate_events(ev: pd.DataFrame, groups: dict, start: str, end: str,
                     known: set) -> pd.DataFrame:
    rows = []
    e = ev[(ev["filing_date"] >= pd.Timestamp(start)) & (ev["filing_date"] <= pd.Timestamp(end))]
    for tk, fd in zip(e["ticker"], e["filing_date"]):
        if tk in ETFS or len(tk) < X2.MIN_TICKER_LEN or tk not in known or tk not in groups:
            continue
        g = groups[tk]
        d = g["date"].to_numpy()
        i = decision_session(d, fd)
        if i is None or i < 260:
            continue
        c = g["close"].to_numpy(float)
        v = g["volume"].to_numpy(float)
        if c[i] < MIN_PRICE:
            continue
        adv = float(np.median((c * v)[i - 62:i + 1]))
        if adv < MIN_ADV:
            continue
        lr = np.diff(np.log(c[i - 63:i + 1]))
        rows.append({"symbol": tk, "t": pd.Timestamp(d[i]), "filing_date": fd, "adv": adv,
                     "vol63": float(np.std(lr, ddof=1)),
                     "delisted_file": bool(g["delisted_file"].iloc[0])})
    out = pd.DataFrame(rows)
    return out.drop_duplicates(["symbol", "t"]) if len(out) else out


def stratified_draw(cand: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """3 size (median dollar volume) x 3 volatility terciles, equal shares."""
    if cand.empty:
        return cand
    c = cand.copy()
    c["size_t"] = pd.qcut(c["adv"].rank(method="first"), 3, labels=False)
    c["vol_t"] = pd.qcut(c["vol63"].rank(method="first"), 3, labels=False)
    rng = np.random.default_rng(seed)
    per = int(math.ceil(n / 9))
    parts = []
    for _, g in c.groupby(["size_t", "vol_t"]):
        idx = rng.permutation(len(g))[:per]
        parts.append(g.iloc[idx])
    out = pd.concat(parts)
    if len(out) > n:
        out = out.iloc[rng.permutation(len(out))[:n]]
    return out.sort_values(["t", "symbol"]).reset_index(drop=True)


# ───────────────────────── plan ─────────────────────────────────────────────
def _case_id(run: str, key: str) -> str:
    return hashlib.sha256(f"{run}|{key}".encode()).hexdigest()[:12]


def build_packets(sample: pd.DataFrame, bars: pd.DataFrame, ev: pd.DataFrame, titles: dict,
                  comnam: dict, sector: dict, *, with_news: bool) -> list:
    syms = sorted(sample["symbol"].unique())
    facts = pd.read_parquet(FACTS, filters=[("ticker", "in", syms)])
    facts["filed"] = pd.to_datetime(facts["filed"])
    facts["end"] = pd.to_datetime(facts["end"], errors="coerce")
    revs = pd.read_parquet(REVS, filters=[("ticker", "in", syms)])
    revs["event_date"] = pd.to_datetime(revs["event_date"], errors="coerce")
    typed = X2.load_typed()
    typed = typed[typed["symbol"].isin(syms)]
    ng: dict = {}
    if with_news:
        news = pd.read_parquet(NEWS, columns=["symbol", "published_utc", "title", "body"],
                               filters=[("symbol", "in", syms)])
        news["pub"] = pd.to_datetime(news["published_utc"], utc=True, errors="coerce")
        news = news.dropna(subset=["pub", "title"])
        ng = {s: g for s, g in news.groupby("symbol")}
    groups = {s: g.reset_index(drop=True) for s, g in bars[bars["symbol"].isin(syms)].groupby("symbol")}
    evd = {s: g["filing_date"].tolist() for s, g in ev[ev["ticker"].isin(syms)].groupby("ticker")}
    fg = {s: g for s, g in facts.groupby("ticker")}
    rg = {s: g for s, g in revs.groupby("ticker")}
    tg = {s: g for s, g in typed.groupby("symbol")}
    out = []
    for r in sample.itertuples(index=False):
        s, t = r.symbol, pd.Timestamp(r.t)
        g = groups[s]
        d = g["date"].to_numpy()
        i = int(np.searchsorted(d, np.datetime64(t), side="right"))
        past = g.iloc[:i]
        pb = price_block(past["close"].to_numpy(), past["volume"].to_numpy())
        ts = str(t.date())
        fb = fundamentals_block(fg.get(s), t)
        sh_now = None
        if s in fg:
            shs = fg[s][fg[s]["fact"] == "shares"].sort_values(["end", "filed"])
            sh_now = float(shs["val"].iloc[-1]) if len(shs) else None
        split = split_factor(fb.get("shares") if fb else None, sh_now)
        if fb and fb.get("shares"):
            fb["shares"] = fb["shares"] * split
        mcap = pb["last_close"] * fb["shares"] if fb and fb.get("shares") else None
        heads = headlines_pit(ng.get(s), t)
        evs = events_pit(tg.get(s), t)
        pk = {"symbol": s, "decision_date": ts, "filing_date": str(pd.Timestamp(r.filing_date).date()),
              "company": titles.get(s) or (comnam.get(s) or "").title(),
              "sector": sector.get(s, "unclassified"), "size_bucket": size_bucket(mcap, pb["adv63_usd"]),
              "price": pb, "fundamentals": fb,
              "analyst": analyst_block(rg.get(s), t, pb["last_close"], split),
              "split_factor_since_t": split,
              "events": evs, "headlines": heads,
              "past_reactions": past_reactions(d, g["close"].to_numpy(float),
                                               [x for x in evd.get(s, []) if x < pd.Timestamp(r.filing_date)], t),
              "delisted_file": bool(r.delisted_file)}
        bad = assert_pit(pk)
        if bad:
            raise AssertionError(f"PIT violation {s} {ts}: {bad[:3]}")
        out.append(pk)
    return out


def famous_sample(ev: pd.DataFrame, groups: dict, known: set) -> pd.DataFrame:
    """The largest 5-session earnings reactions of mega-liquid names in
    2018-01..2025-06, one per name: the cases a model most plausibly remembers."""
    cand = candidate_events(ev, groups, "2018-01-01", "2025-06-30", known)
    cand = cand[cand["adv"] >= 1e9]
    mv = []
    for r in cand.itertuples(index=False):
        g = groups[r.symbol]
        d = g["date"].to_numpy()
        i = int(np.searchsorted(d, np.datetime64(r.t), side="right")) - 1
        c = g["close"].to_numpy(float)
        mv.append(abs(c[i + H_SHORT] / c[i] - 1) if i + H_SHORT < len(c) else 0.0)
    cand = cand.assign(absmove=mv).sort_values("absmove", ascending=False)
    return cand.drop_duplicates("symbol").head(N_FAMOUS).drop(columns="absmove").sort_values("t")


def stage_plan(run: str, part: str) -> dict:
    from backend.services import disk_guard as DG                      # noqa: PLC0415
    rd = RUN_ROOT / run
    for sub in ("sealed", "cases", "batches", "answers", "rows"):
        (rd / sub).mkdir(parents=True, exist_ok=True)
    reg_sha = (hashlib.sha256(REGISTRATION.read_bytes()).hexdigest()
               if REGISTRATION.exists() else None)
    titles, comnam, sector = load_names_sectors()
    known = set(titles) | set(comnam)
    ev = load_events()
    bars = load_bars("2017-01-01")
    groups = {s_: g.reset_index(drop=True) for s_, g in bars.groupby("symbol", sort=False)}
    samples = {}
    if part == "clean":
        cand = candidate_events(ev, groups, CLEAN_START, CLEAN_END, known)
        cand = cand[cand["t"] >= pd.Timestamp(CLEAN_START)]      # the DECISION date, not the filing
        samples["clean"] = stratified_draw(cand, N_CLEAN, SEED)
        samples["famous"] = famous_sample(ev, groups, known)
    else:
        cand = candidate_events(ev, groups, BACKTEST_START, BACKTEST_END, known)
        cand["week"] = cand["t"].dt.to_period("W-SUN")
        wk = cand.groupby("week").size()
        wk = wk[wk >= 150].index.sort_values()
        pick = [wk[int(round(x))] for x in np.linspace(0, len(wk) - 1, N_BACKTEST_BLOCKS)]
        samples["backtest"] = stratified_draw(cand[cand["week"].isin(pick)].drop(columns="week"),
                                              N_BACKTEST, SEED + 1)
    real_tickers = frozenset(groups)
    plan = {"run": run, "part": part, "generated_at": datetime.now(timezone.utc).isoformat(),
            "registration": str(REGISTRATION.relative_to(ROOT)), "registration_sha256": reg_sha,
            "amnesia_vendored_from": str(AMNESIA_SRC), "amnesia_sha256": AMNESIA_SHA256,
            "amnesia_sha256_now": (hashlib.sha256(AMNESIA_SRC.read_bytes()).hexdigest()
                                   if AMNESIA_SRC.exists() else None),
            "forecast_system_sha256": hashlib.sha256(FORECAST_SYSTEM.encode()).hexdigest(),
            "levels": LEVELS, "cases": [], "leak_refusals": [], "dropped_headlines": 0,
            "sample_sizes": {}, "packets": []}
    for sub_part, smp in samples.items():
        packets = build_packets(smp, bars, ev, titles, comnam, sector, with_news=True)
        plan["sample_sizes"][sub_part] = {"n": len(packets), "n_symbols": int(smp["symbol"].nunique()),
                                          "n_week_blocks": int(smp["t"].dt.to_period("W-SUN").nunique()),
                                          "n_delisted_file": int(smp["delisted_file"].sum()),
                                          "first": str(smp["t"].min().date()),
                                          "last": str(smp["t"].max().date())}
        for pk in packets:
            key = f"{sub_part}|{pk['symbol']}|{pk['decision_date']}"
            al = aliases_for(pk["symbol"], titles, comnam)
            for level in LEVELS:
                cid = _case_id(run, f"{key}|{level}|forecast")
                can = _case_id(run, f"{key}|{level}|canary")
                m = case_mapping(key, level, real_tickers,
                                 int(hashlib.sha256(key.encode()).hexdigest()[:8], 16))
                if level == "A2_MASKED":
                    m["k_price"] = 100.0 / pk["price"]["last_close"]
                text, dropped = render_case(pk, level, m, al, cid)
                plan["dropped_headlines"] += dropped
                viol = scan_case(text, level, pk, al)
                if level == "A0_NAMED":
                    ctext = canary_user(level, "", company=pk["company"], ticker=pk["symbol"],
                                        date=pk["decision_date"])
                else:
                    ctext = canary_user(level, text.replace(f"CASE {cid}\n", ""))
                plan["cases"].append({"case_id": cid, "canary_id": can, "part": sub_part,
                                      "level": level, "key": key, "symbol": pk["symbol"],
                                      "decision_date": pk["decision_date"], "company": pk["company"],
                                      "aliases": al, "mapping": m, "text": text,
                                      "canary_text": ctext, "violations": viol,
                                      "refused": bool(viol)})
                if viol:
                    plan["leak_refusals"].append({"case_id": cid, "level": level,
                                                  "violations": viol[:5]})
            # a situation whose mask cannot be verified at A2 OR A3 leaves the
            # sample at EVERY level, so the levels stay paired row for row
            mine = [c for c in plan["cases"] if c["key"] == key]
            if any(c["refused"] for c in mine):
                for c in mine:
                    if not c["refused"]:
                        c["refused"] = True
                        c["violations"] = [{"kind": "pair_refused", "match": "another level leaked"}]
            plan["packets"].append({"key": key, **pk})
    DG.atomic_write_json(rd / "sealed" / f"plan_{part}.json", plan)
    if part == "clean":
        write_file_arm(rd, plan)
    n_ok = sum(1 for c in plan["cases"] if not c["refused"])
    print(json.dumps({"part": part, "sample_sizes": plan["sample_sizes"], "cases": len(plan["cases"]),
                      "not_refused": n_ok, "leak_refusals": len(plan["leak_refusals"]),
                      "dropped_headlines": plan["dropped_headlines"],
                      "registration_sha256": reg_sha}, indent=1))
    return plan


INSTRUCTIONS = """# ANSWERING INSTRUCTIONS (file arm, AMNESIA-2 / fiction backtest)

You are answering case files for a forecasting test. Each case file is
self-contained: it states its own question and the answer format.

RULES (all binding):
1. Read ONLY the case files listed in the batch file you were given
   (`batches/<batch>.txt`, one case id per line) and this instructions file.
   Each case lives at `cases/<case_id>.txt`.
2. Write each answer to `answers/<YOUR_ARM_NAME>/<case_id>.txt` (the arm name
   is given to you by whoever started you; create the folder if needed).
   The answer file contains ONLY what the case asks for (one JSON object, no
   prose, no markdown).
3. Use no tool other than reading those case files and writing those answer
   files. Do NOT search the web. Do NOT open, list or search any other file or
   folder in this repository or on this machine. In particular never open
   `sealed/`, `rows/`, any receipt, `answers/` of any other arm, or any file
   outside this run folder. The case files never mention those folders and you
   do not need them.
4. Answer each case independently, from the case text alone. Do not try to
   identify the real company or the real date in order to recall what happened;
   if a canary case asks whether you can identify a company, answer honestly
   from the text as given, and say UNKNOWN when you do not know.
5. Every case must be answered; if you cannot, write the single word REFUSED.

The folder you work in is the run folder that contains this file.
"""


def write_file_arm(rd: Path, plan: dict) -> None:
    """Case files for the file arm: clean part at A2 and A3, famous part at all
    three levels, each forecast and its canary as separate cases. Batches never
    mix levels, kinds or parts, so two versions of one situation never meet."""
    (rd / "ANSWERING_INSTRUCTIONS.md").write_text(INSTRUCTIONS, encoding="utf-8")
    batches: dict = {}
    for c in plan["cases"]:
        if c["refused"] or c["part"] == "backtest":
            continue
        if c["part"] == "clean" and c["level"] not in FILE_ARM_LEVELS:
            continue
        (rd / "cases" / f"{c['case_id']}.txt").write_text(
            case_file_text("forecast", c["text"]), encoding="utf-8")
        (rd / "cases" / f"{c['canary_id']}.txt").write_text(
            case_file_text("canary", c["canary_text"]), encoding="utf-8")
        batches.setdefault((c["part"], c["level"], "canary"), []).append(c["canary_id"])
        batches.setdefault((c["part"], c["level"], "forecast"), []).append(c["case_id"])
    order = sorted(batches, key=lambda k: (k[0] != "famous", k[2] != "canary", k[1]))
    idx = []
    n = 0
    for k in order:
        ids = batches[k]
        rng = np.random.default_rng(int(hashlib.sha256("|".join(k).encode()).hexdigest()[:8], 16))
        ids = [ids[i] for i in rng.permutation(len(ids))]
        for j in range(0, len(ids), 20):
            n += 1
            name = f"batch_{n:03d}"
            (rd / "batches" / f"{name}.txt").write_text("\n".join(ids[j:j + 20]) + "\n", encoding="utf-8")
            idx.append({"batch": name, "part": k[0], "level": k[1], "kind": k[2],
                        "n": len(ids[j:j + 20])})
    # the index names parts and levels; it lives in sealed/, which agents never open
    (rd / "sealed" / "batch_index.json").write_text(json.dumps(idx, indent=1), encoding="utf-8")


# ───────────────────────── run ──────────────────────────────────────────────
def load_plan(rd: Path, part: str) -> dict:
    return json.loads((rd / "sealed" / f"plan_{part}.json").read_text(encoding="utf-8"))


def done_keys(path: Path) -> set:
    if not path.exists():
        return set()
    return {(r["case_id"], r["kind"]) for r in
            (json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())}


_write_lock = threading.Lock()


def one_call(arm: Arm, budget: Optional[Budget], c: dict, kind: str, rows_path: Path,
             raw_path: Path, run: str) -> dict:
    """One frozen row: arm, level, the model that ACTUALLY answered, case id."""
    system = FORECAST_SYSTEM if kind == "forecast" else CANARY_SYSTEM
    user = c["text"] if kind == "forecast" else c["canary_text"]
    cid = c["case_id"] if kind == "forecast" else c["canary_id"]
    res_ = budget.reserve() if (budget is not None and arm.paid) else 0.0
    try:
        r = arm.answer(system, user, cid)
    except Exception as e:                                              # noqa: BLE001
        r = {"text": None, "ok": False, "status": "EXCEPTION", "cost_usd": None if arm.paid else 0.0,
             "served_model": None, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    rec_call = {"arm": arm.name, "case_id": c["case_id"], "kind": kind, "ok": r.get("ok"),
                "status": r.get("status"), "served_model": r.get("served_model"),
                "cost_usd": r.get("cost_usd"), "tokens_in": r.get("tokens_in"),
                "tokens_out": r.get("tokens_out"), "at": datetime.now(timezone.utc).isoformat()}
    if budget is not None and arm.paid:
        budget.settle(res_, rec_call)
    if kind == "forecast":
        parsed, why = parse_forecast(r.get("text")) if r.get("ok") else (None, r.get("status"))
    else:
        parsed, why = parse_canary(c["level"], r.get("text")) if r.get("ok") else (None, r.get("status"))
    row = {"run": run,
           "row_id": hashlib.sha256(f"{arm.name}|{c['case_id']}|{kind}".encode()).hexdigest()[:16],
           "case_id": c["case_id"], "kind": kind, "arm": arm.name, "level": c["level"],
           "part": c["part"], "model_requested": arm.model_id, "model_served": r.get("served_model"),
           "status": r.get("status"), "parsed_ok": parsed is not None, "refusal": why,
           "answer": parsed, "cost_usd": r.get("cost_usd"),
           "raw_probability": (parsed or {}).get("p_beat_median_5d") if kind == "forecast" else None,
           "shrink_basis": "none: arm reliability unmeasured until graded",
           "frozen_at": datetime.now(timezone.utc).isoformat(),
           "licence": "PRODUCT_EXPERIMENT", "no_capital_authority": True}
    with _write_lock:
        with open(rows_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        with open(raw_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"case_id": c["case_id"], "kind": kind, "arm": arm.name,
                                 "text": (r.get("text") or "")[:4000]}) + "\n")
    return row


def arm_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def stage_run(run: str, arm_spec: str, parts: list, levels: list, limit: Optional[int],
              workers: int, model_id: Optional[str] = None, allow_local: bool = False,
              kinds=("canary", "forecast")) -> dict:
    rd = RUN_ROOT / run
    arm = make_arm(arm_spec, rd, model_id, allow_local)
    budget = Budget(CAP_USD, rd / "calls.jsonl")
    rows_path = rd / "rows" / f"{arm_slug(arm.name)}.jsonl"
    raw_path = rd / "rows" / f"{arm_slug(arm.name)}_raw_local.jsonl"
    done = done_keys(rows_path)
    plan = load_plan(rd, "clean" if set(parts) <= {"clean", "famous"} else "backtest")
    todo = []
    for c in plan["cases"]:
        if c["part"] not in parts or c["level"] not in levels or c["refused"]:
            continue
        for kind in kinds:      # the canary first, exactly as AMNESIA-1 did
            if (c["case_id"], kind) not in done:
                todo.append((c, kind))
    if limit is not None:
        todo = todo[:limit]
    n, t0 = 0, time.time()
    stopped = None
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one_call, arm, budget, c, k, rows_path, raw_path, run) for c, k in todo]
        for f in as_completed(futs):
            try:
                f.result()
                n += 1
            except CapRefused as e:
                stopped = str(e)
            if n and n % 100 == 0:
                print(f"{n}/{len(todo)} spent ${budget.spent:.4f} {time.time() - t0:.0f}s", flush=True)
    out = {"arm": arm.name, "calls": n, "todo": len(todo), "spent_run_usd": round(budget.spent, 5),
           "cap_stop": stopped}
    print(json.dumps(out), flush=True)
    return out


def stage_probe_nvidia(run: str, model: Optional[str]) -> dict:
    """ONE call. The key is never printed; only whether it answered."""
    rd = RUN_ROOT / run
    rd.mkdir(parents=True, exist_ok=True)
    arm = make_arm("nvidia" + (f":{model}" if model else ""), rd)
    r = arm.answer("Answer in English.", "Reply with the single word OK.", "probe")
    out = {"model": arm.model_id, "ok": r["ok"], "status": r["status"],
           "served_model": r.get("served_model"), "text": (r.get("text") or "")[:40],
           "error": (r.get("error") or "")[:160], "at": datetime.now(timezone.utc).isoformat()}
    (rd / f"receipt_nvidia_probe_{arm_slug(arm.model_id or '')}.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out))
    return out


def stage_ingest(run: str, arm_spec: str, model_id: Optional[str]) -> dict:
    """Parse the file arm's answer files into frozen rows (no network)."""
    rd = RUN_ROOT / run
    arm = make_arm(arm_spec, rd, model_id)
    rows_path = rd / "rows" / f"{arm_slug(arm.name)}.jsonl"
    raw_path = rd / "rows" / f"{arm_slug(arm.name)}_raw_local.jsonl"
    done = done_keys(rows_path)
    plan = load_plan(rd, "clean")
    n = 0
    for c in plan["cases"]:
        if c["refused"] or (c["part"] == "clean" and c["level"] not in FILE_ARM_LEVELS):
            continue
        for kind in ("canary", "forecast"):
            cid = c["case_id"] if kind == "forecast" else c["canary_id"]
            if (c["case_id"], kind) in done or not arm.path_for(cid).is_file():
                continue
            one_call(arm, None, c, kind, rows_path, raw_path, run)
            n += 1
    print(json.dumps({"arm": arm.name, "ingested": n}))
    return {"ingested": n}


# ───────────────────────── outcomes + grading ───────────────────────────────
def outcomes_for(packets: list, bars: pd.DataFrame) -> pd.DataFrame:
    """Computed at ANALYSIS time (the plan holds no outcome): forward returns
    from the decision close (the last close if the name stopped trading inside
    the window, flagged), the median stock's return over the same window
    (universe: close >= $3 and dollar volume >= $1M on t), and the 12-1
    momentum baseline's call (its 12-1 return above the cross-sectional median)."""
    cal = np.array(sorted(bars["date"].unique()))
    wide = bars.pivot_table(index="date", columns="symbol", values="close")
    dvw = (bars.assign(dv=bars["close"] * bars["volume"])
               .pivot_table(index="date", columns="symbol", values="dv"))
    med: dict = {}
    mom_med: dict = {}
    rows = []
    for pk in packets:
        t = pd.Timestamp(pk["decision_date"])
        i = int(np.searchsorted(cal, np.datetime64(t)))
        rec = {"key": pk["key"], "symbol": pk["symbol"], "decision_date": pk["decision_date"]}
        s = wide[pk["symbol"]] if pk["symbol"] in wide.columns else None
        for h in (H_SHORT, H_LONG):
            rec[f"r{h}"] = None
            rec[f"beat{h}"] = None
            if s is None or i + h >= len(cal):
                continue
            c0 = s.iloc[i]
            fwd = s.iloc[i + 1:i + h + 1].dropna()
            if not len(fwd) or not np.isfinite(c0):
                continue
            rec[f"r{h}"] = float(fwd.iloc[-1] / c0 - 1) * 100
            rec[f"delisted_in_h{h}"] = bool(len(fwd) < h)
            if (t, h) not in med:
                row0 = wide.iloc[i]
                ok = (row0 >= MIN_PRICE) & (dvw.iloc[i] >= MEDIAN_UNIVERSE_MIN_DV)
                med[(t, h)] = float(((wide.iloc[i + h] / row0 - 1)[ok].dropna() * 100).median())
            rec[f"med{h}"] = med[(t, h)]
            rec[f"beat{h}"] = int(rec[f"r{h}"] > med[(t, h)])
        if t not in mom_med and i >= 252:
            row0 = wide.iloc[i]
            ok = (row0 >= MIN_PRICE) & (dvw.iloc[i] >= MEDIAN_UNIVERSE_MIN_DV)
            mom_med[t] = float((wide.iloc[i - 21] / wide.iloc[i - 252] - 1)[ok].dropna().median())
        mm = pk["price"]["summary"].get("mom_12_1_pct")
        rec["mom_call"] = (int(mm / 100 > mom_med[t]) if (t in mom_med and mm is not None
                                                          and np.isfinite(mm)) else None)
        rec["sd_prior_vol"] = pk["price"]["summary"]["vol_63d_daily_pct"] * math.sqrt(H_SHORT)
        pr = [abs(v) for _, v in pk.get("past_reactions") or []]
        rec["sd_prior_earn"] = (float(np.median(pr)) / 0.6745 if len(pr) >= 2 else None)
        rec["week"] = str(t.to_period("W-SUN"))
        rows.append(rec)
    return pd.DataFrame(rows)


def interval_score(y, lo, hi, alpha: float = 0.2):
    """Gneiting-Raftery interval score for a central (1-alpha) interval (lower is better)."""
    y, lo, hi = (np.asarray(x, float) for x in (y, lo, hi))
    return (hi - lo) + (2 / alpha) * (lo - y) * (y < lo) + (2 / alpha) * (y - hi) * (y > hi)


def _block(x: pd.Series, blocks: pd.Series) -> dict:
    d = pd.DataFrame({"x": np.asarray(x, float), "b": np.asarray(blocks)}).dropna()
    return X2._date_block(d.groupby("b")["x"].mean())


def _spearman(a, b) -> float:
    a, b = pd.Series(a).rank(), pd.Series(b).rank()
    return float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 and a.std() > 0 and b.std() > 0 else float("nan")


def partial_rank_corr(f, y, ctrl) -> float:
    """Spearman of f with y after removing the rank-linear part of ctrl from both."""
    d = pd.DataFrame({"f": np.asarray(f, float), "y": np.asarray(y, float),
                      "c": np.asarray(ctrl, float)}).dropna()
    if len(d) < 8:
        return float("nan")
    R = d.rank()
    X = np.column_stack([np.ones(len(R)), R["c"]])
    res = {}
    for k in ("f", "y"):
        beta, *_ = np.linalg.lstsq(X, R[k].to_numpy(float), rcond=None)
        res[k] = R[k].to_numpy(float) - X @ beta
    if res["f"].std() == 0 or res["y"].std() == 0:
        return float("nan")
    return float(np.corrcoef(res["f"], res["y"])[0, 1])


#: DECLARED BEFORE THE FIRST PAID CALL (2026-09-28), per cell = arm x level x part:
#:  DIR   : 5-session p_beat hit rate: Wilson95 low > 0.5 AND week-block t >= 2
#:  BETA  : DIR and hit <= the 12-1 momentum baseline's hit on the same rows
#:  MAG   : interval score of the model's 80% 5-session range minus the trailing-vol
#:          prior's < 0 with week-block t <= -2 (VOL), and ALSO minus the stock's own
#:          past-earnings-reaction prior < 0 with t <= -2 (EARN)
#:  direction verdict: ALPHA_DETECTED if DIR and not BETA; BETA_EXPLAINS if DIR and BETA;
#:     FAILED_VARIANT if not DIR and Wilson95 high < 0.55; else CANNOT_DISTINGUISH
#:  magnitude verdict: ALPHA_DETECTED if VOL and EARN; BETA_EXPLAINS if VOL and not EARN
#:     (it knew an earnings report was due, which the earnings prior already knows);
#:     FAILED_VARIANT if the diff vs the vol prior is > 0 with t >= 2; else CANNOT_DISTINGUISH
#:  LEAK (famous part): the fiction LEAKS if A3 identifies the company on > 10% of
#:     canaries OR the A3 hit rate on famous 5-session moves is >= 0.70
RULE = ("DIR: wilson_lo>0.5 & week t>=2; BETA: DIR & hit<=momentum hit; MAG: IS diff vs vol prior "
        "<0 t<=-2 and vs earnings prior <0 t<=-2; LEAK: A3 canary id >10% or A3 famous hit >=0.70")


def grade_cell(g: pd.DataFrame) -> dict:
    from backend.services import protocol_p16 as PP                     # noqa: PLC0415
    out: dict = {"n": int(len(g)), "n_weeks": int(g["week"].nunique())}
    for h in (H_SHORT, H_LONG):
        k = f"p_beat_median_{h}d"
        d = g[g[f"beat{h}"].notna()]
        if d.empty:
            out[f"dir{h}"] = {"n": 0, "note": "outcome not matured"}
            continue
        y = d[f"beat{h}"].astype(int)
        p = d[k].astype(float)
        hit = ((p > 0.5).astype(int) == y).astype(float)
        hit[p == 0.5] = 0.5
        kk, n = float(hit.sum()), len(hit)
        mom = d[d["mom_call"].notna()]
        mh = (mom["mom_call"].astype(int) == mom[f"beat{h}"].astype(int)).astype(float)
        base = float(y.mean())
        rel = []
        for lo in np.arange(0, 1.0, 0.1):
            b = d[(p >= lo) & (p < lo + 0.1 + (1e-9 if lo >= 0.85 else 0))]
            if len(b):
                rel.append({"bin": f"{lo:.1f}-{lo + 0.1:.1f}", "n": int(len(b)),
                            "mean_p": float(b[k].mean()), "freq": float(b[f"beat{h}"].mean())})
        out[f"dir{h}"] = {
            "n": n, "hit": kk / n, "wilson95": X2.wilson(int(round(kk)), n),
            "week_block": _block(hit - 0.5, d["week"]),
            "momentum_hit_same_rows": float(mh.mean()) if len(mh) else None,
            "model_minus_momentum": (_block(hit.loc[mom.index] - mh, mom["week"]) if len(mh) else None),
            "brier": float(((p - y) ** 2).mean()), "brier_base_rate": float(((base - y) ** 2).mean()),
            "brier_coin": 0.25, "base_rate": base, "mean_p": float(p.mean()), "sd_p": float(p.std()),
            "ece": PP.ece(p.tolist(), y.tolist()).get("ece"), "reliability": rel,
            "auc": auc(p.to_numpy(), y.to_numpy()), **abstention(p.to_numpy(), y.to_numpy())}
    d = g[g["r5"].notna()]
    if len(d):
        y = d["r5"].astype(float)
        z = 1.2815516
        is_m = interval_score(y, d["low80_5d_pct"], d["high80_5d_pct"])
        is_v = interval_score(y, -z * d["sd_prior_vol"], z * d["sd_prior_vol"])
        e = d[d["sd_prior_earn"].notna()]
        is_e = interval_score(e["r5"], -z * e["sd_prior_earn"].astype(float), z * e["sd_prior_earn"].astype(float))
        is_me = interval_score(e["r5"], e["low80_5d_pct"], e["high80_5d_pct"])
        sc = [(s["prob"], int(s["ret_low_pct"] <= r5 <= s["ret_high_pct"]))
              for r5, ss in zip(y, d["scenarios"]) for s in ss]
        sc = pd.DataFrame(sc, columns=["p", "in"])
        srel = []
        for lo in np.arange(0, 1, 0.2):
            b = sc[(sc["p"] >= lo) & (sc["p"] < lo + 0.2 + (1e-9 if lo >= 0.75 else 0))]
            if len(b):
                srel.append({"bin": f"{lo:.1f}-{lo + 0.2:.1f}", "n": int(len(b)),
                             "mean_p": float(b["p"].mean()), "freq": float(b["in"].mean())})
        mass_in = [sum(s["prob"] for s in ss if s["ret_low_pct"] <= r5 <= s["ret_high_pct"])
                   for r5, ss in zip(y, d["scenarios"])]
        out["range5"] = {
            "n": int(len(d)),
            "coverage_80_model": float(((y >= d["low80_5d_pct"]) & (y <= d["high80_5d_pct"])).mean()),
            "coverage_80_vol_prior": float((y.abs() <= z * d["sd_prior_vol"]).mean()),
            "coverage_80_earnings_prior": (float((e["r5"].abs() <= z * e["sd_prior_earn"]).mean())
                                           if len(e) else None),
            "median_width_model_over_vol_prior": float(((d["high80_5d_pct"] - d["low80_5d_pct"]) /
                                                        (2 * z * d["sd_prior_vol"])).median()),
            "interval_score_model": float(is_m.mean()), "interval_score_vol_prior": float(is_v.mean()),
            "diff_vs_vol_prior": _block(is_m - is_v, d["week"]),
            "n_with_earnings_prior": int(len(e)),
            "interval_score_model_on_earn_rows": float(is_me.mean()) if len(e) else None,
            "interval_score_earnings_prior": float(is_e.mean()) if len(e) else None,
            "diff_vs_earnings_prior": (_block(is_me - is_e, e["week"]) if len(e) > 2 else None),
            "scenario_reliability": srel,
            "mean_prob_mass_on_scenarios_containing_outcome": float(np.mean(mass_in))}
        feats = {}
        for f in FEATURES:
            x = d["features"].map(lambda z_: z_[f]).astype(float)
            per = []
            for _, gg in d.groupby("week"):
                if len(gg) >= 8:
                    v = partial_rank_corr(x[gg.index], gg["r5"].abs(), np.log(gg["sd_prior_vol"]))
                    if np.isfinite(v):
                        per.append(v)
            per = pd.Series(per, dtype=float)
            feats[f] = {"pooled_partial_spearman_vs_abs_r5_ctrl_vol":
                            partial_rank_corr(x, y.abs(), np.log(d["sd_prior_vol"])),
                        "raw_spearman_vs_abs_r5": _spearman(x, y.abs()),
                        "week_block": (X2._date_block(per) if len(per) > 1 else {"n_dates": len(per)}),
                        "mean": float(x.mean()), "sd": float(x.std())}
        out["features"] = feats
    return out


ABSTAIN_SD = 0.03          # sd of p below this = the model declined to forecast (0.50 +/- a tilt)
LEAK_ID_RATE = 0.10        # registered: A3 famous identified on > 10% of canaries -> the fiction leaks
LEAK_HIT = 0.70            # registered: A3 famous hit rate >= 0.70 -> the fiction leaks


def auc(p, y) -> float | None:
    """Mann-Whitney AUC of p against the binary outcome y (ties count half)."""
    p, y = np.asarray(p, float), np.asarray(y, int)
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    r = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def abstention(p, y) -> dict:
    """How much of a direction cell is the model declining to forecast."""
    p, y = np.asarray(p, float), np.asarray(y, int)
    tie = p == 0.5
    side = ~tie
    hit_side = float(((p[side] > 0.5).astype(int) == y[side]).mean()) if side.any() else None
    return {"share_p_exactly_half": float(tie.mean()) if len(p) else None,
            "n_took_a_side": int(side.sum()), "hit_when_took_a_side": hit_side,
            "abstained": bool(len(p) and float(np.std(p, ddof=1)) < ABSTAIN_SD)}


def leak_table(F: pd.DataFrame, canaries: dict) -> dict:
    """The registered leak rule per arm, over EVERY arm that answered the famous A3 canaries or
    the famous forecasts. A clause with no data is NOT_EVALUATED, never 'passed' (amended
    2026-09-29: the Opus arm answered the canaries only and got no leak verdict at all)."""
    hits: dict = {}
    if F is not None and len(F):
        for arm, g in F[F["part"] == "famous"].groupby("arm"):
            for lv, gg in g.groupby("level"):
                d = gg[gg["beat5"].notna()]
                hits.setdefault(arm, {})[lv] = (float(((d["p_beat_median_5d"] > 0.5).astype(int)
                                                       == d["beat5"].astype(int)).mean()) if len(d) else None)
    arms = set(hits) | {k.split("|")[0] for k in canaries if k.endswith("|famous|A3_SYNTHETIC")}
    out = {}
    for arm in sorted(arms):
        cr = canaries.get(f"{arm}|famous|A3_SYNTHETIC") or {}
        idr = cr.get("identified_rate")
        h3 = (hits.get(arm) or {}).get("A3_SYNTHETIC")
        clauses = {"identified_rate_gt_10pct": (None if idr is None else bool(idr > LEAK_ID_RATE)),
                   "famous_A3_hit_ge_0.70": (None if h3 is None else bool(h3 >= LEAK_HIT))}
        fired = [k for k, v in clauses.items() if v]
        evaluated = [k for k, v in clauses.items() if v is not None]
        out[arm] = {"famous_hit_by_level": hits.get(arm, {}), "A3_canary_identified_rate": idr,
                    "A3_canary_identified": cr.get("identified_company"), "A3_canary_n": cr.get("n"),
                    "clauses": clauses, "clauses_evaluated": evaluated,
                    "fiction_leaks": (True if fired else (False if len(evaluated) == 2 else
                                                          (None if not evaluated else "NOT_FIRED_ON_PARTIAL_EVIDENCE")))}
    return out


def stage_amend(run: str, *, note: str = "") -> dict:
    """A NEW receipt beside receipt_analyze.json (which is never rewritten): the direction cells
    re-read with AUC and the abstention figures, and the registered leak rule for every arm.
    No model is called."""
    from backend.services import disk_guard as DG                      # noqa: PLC0415
    rd = RUN_ROOT / run
    base = json.loads((rd / "receipt_analyze.json").read_text(encoding="utf-8"))
    plan = load_plan(rd, "clean")
    cases = {c["case_id"]: c for c in plan["cases"]}
    packets = plan["packets"]
    allb = load_bars("2017-01-01")
    cal = np.array(sorted(allb["date"].unique()))
    need = set()
    for pk in packets:
        i = int(np.searchsorted(cal, np.datetime64(pd.Timestamp(pk["decision_date"]))))
        for j in (i - 252, i - 21, i, i + H_SHORT, i + H_LONG):
            if 0 <= j < len(cal):
                need.add(pd.Timestamp(cal[j]))
    syms = {pk["symbol"] for pk in packets}
    oc = outcomes_for(packets, allb[allb["symbol"].isin(syms) | allb["date"].isin(need)]
                      .sort_values(["symbol", "date"]))
    del allb
    okey = {k: r for k, r in zip(oc["key"], oc.to_dict("records"))}
    rows = []
    for f in sorted((rd / "rows").glob("*.jsonl")):
        if not f.name.endswith("_raw_local.jsonl"):
            rows += [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    R = pd.DataFrame(rows)
    fc = R[(R["kind"] == "forecast") & R["parsed_ok"]]
    flat = []
    for _, r in fc.iterrows():
        o = okey.get(cases[r["case_id"]]["key"]) if r["case_id"] in cases else None
        if o is None:
            continue
        flat.append({"arm": r["arm"], "level": r["level"], "part": r["part"], **o,
                     "p5": float(r["answer"]["p_beat_median_5d"])})
    F = pd.DataFrame(flat)
    cells = {}
    for (arm, part, level), g in F.groupby(["arm", "part", "level"]):
        d = g[g["beat5"].notna()]
        y = d["beat5"].astype(int).to_numpy()
        p = d["p5"].to_numpy()
        prior = (base.get("cells") or {}).get(f"{arm}|{part}|{level}", {})
        cells[f"{arm}|{part}|{level}"] = {"n": int(len(d)), "auc": auc(p, y), "sd_p": float(np.std(p, ddof=1)),
                                           **abstention(p, y),
                                           "formal_direction_verdict": (prior.get("verdicts") or {}).get("direction")}
    famous_F = F.rename(columns={"p5": "p_beat_median_5d"}) if len(F) else F
    rec = {"experiment": "AMNESIA-2 amendment (no model called)", "run": run,
           "amends": "receipt_analyze.json (unchanged on disk)", "generated_at": datetime.now(timezone.utc).isoformat(),
           "rule_leak": f"A3 famous identified > {LEAK_ID_RATE:.0%} of canaries OR A3 famous hit >= {LEAK_HIT}",
           "abstain_sd": ABSTAIN_SD, "cells": cells,
           "leak_test": leak_table(famous_F, base.get("canaries") or {}),
           "provenance_note": ("the file arm's answering agents were full coding sub-agents with file, "
                               "shell and web tools; their confinement was an instruction "
                               "(ANSWERING_INSTRUCTIONS.md rule 3), sealed/ sat one directory away, and "
                               "no tool-call log was kept. The harness test pins only the READER's "
                               "confinement."), "note": note}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = rd / f"receipt_amendment_{stamp}.json"
    DG.atomic_write_json(out, rec)
    print(json.dumps({"out": str(out), "leak_test": rec["leak_test"],
                      "opus": {k: v for k, v in cells.items() if "opus" in k}}, indent=1, default=str))
    return rec


def _t(block: dict) -> float:
    """A block's t, with a zero-spread block read as +/-inf by its mean's sign
    (X2._date_block returns NaN there, which would hide a perfect score)."""
    t = block.get("t", float("nan"))
    if not np.isfinite(t) and block.get("se") == 0 and block.get("mean_excess_over_half"):
        return math.copysign(float("inf"), block["mean_excess_over_half"])
    return t


def verdicts(cell: dict) -> dict:
    v = {}
    d = cell.get("dir5") or {}
    if d.get("n"):
        lo, hi = d["wilson95"]
        t = _t(d["week_block"])
        dir_ok = bool(lo > 0.5 and t >= 2)
        beta = bool(dir_ok and d["momentum_hit_same_rows"] is not None
                    and d["hit"] <= d["momentum_hit_same_rows"])
        v["direction"] = ("ALPHA_DETECTED" if dir_ok and not beta else "BETA_EXPLAINS" if dir_ok
                          else "FAILED_VARIANT" if hi < 0.55 else "CANNOT_DISTINGUISH")
        if d.get("abstained"):
            # the formal rule is printed unchanged; the READING is that the model declined to
            # forecast, which measures no skill either way (REVIEW_2026-09-29_FICTION_BACKTEST 1)
            v["direction_reading"] = (f"CANNOT_DISTINGUISH (model abstained: sd_p {d['sd_p']:.3f}, "
                                      f"{d['share_p_exactly_half']:.0%} of p exactly 0.50)")
    r = cell.get("range5")
    if r:
        dv = r["diff_vs_vol_prior"]
        de = r.get("diff_vs_earnings_prior") or {}
        vol = bool(dv.get("mean_excess_over_half", 1) < 0 and _t(dv) <= -2)
        earn = bool(de.get("mean_excess_over_half", 1) < 0 and _t(de) <= -2)
        v["magnitude"] = ("ALPHA_DETECTED" if vol and earn else "BETA_EXPLAINS" if vol
                          else "FAILED_VARIANT" if (dv.get("mean_excess_over_half", 0) > 0
                                                    and _t(dv) >= 2)
                          else "CANNOT_DISTINGUISH")
    return v


def canary_table(can: pd.DataFrame, plan_cases: dict) -> dict:
    out = {}
    for (arm, part, level), g in can.groupby(["arm", "part", "level"]):
        ok = g[g["parsed_ok"]]
        rec: dict = {"n": int(len(g)), "parsed": int(len(ok))}
        if level == "A0_NAMED":
            yes = [a for a in ok["answer"] if a["recall"] == "YES"]
            rec["recall_yes"] = len(yes)
            rec["recall_yes_rate"] = len(yes) / len(ok) if len(ok) else None
        else:
            hits = yhits = 0
            for cid, a in zip(ok["case_id"], ok["answer"]):
                c = plan_cases[cid]
                name_ok = (a["ticker"] == c["symbol"] or
                           any(al.lower() in a["company"].lower() for al in c["aliases"] if len(al) >= 4))
                hits += int(name_ok)
                yhits += int(a["year"] == int(c["decision_date"][:4]))
            rec["identified_company"] = hits
            rec["identified_rate"] = hits / len(ok) if len(ok) else None
            rec["year_correct"] = yhits
            rec["year_correct_rate"] = yhits / len(ok) if len(ok) else None
        out[f"{arm}|{part}|{level}"] = rec
    return out


AUGUST_TABLE = [
    {"arm": "A0 named, no instruction", "brier": 0.2495, "auc": 0.550, "canary": "recall 15.8%"},
    {"arm": "A1 named + suppression instruction", "brier": 0.2530, "auc": 0.532, "canary": "recall 15.8%"},
    {"arm": "A2 masked", "brier": 0.2568, "auc": 0.519, "canary": "identified 0/120"},
    {"arm": "A3 synthetic", "brier": 0.2564, "auc": 0.521, "canary": "identified 0/120"},
    {"arm": "climatology", "brier": 0.2500, "auc": None, "canary": "-"},
    {"arm": "logistic, 5 features, OOS", "brier": 0.2538, "auc": 0.511, "canary": "-"},
]


def stage_analyze(run: str) -> dict:
    from backend.services import disk_guard as DG                      # noqa: PLC0415
    rd = RUN_ROOT / run
    plan = load_plan(rd, "clean")
    cases = {c["case_id"]: c for c in plan["cases"]}
    packets = plan["packets"]
    allb = load_bars("2017-01-01")
    cal = np.array(sorted(allb["date"].unique()))
    need = set()
    for p in packets:
        i = int(np.searchsorted(cal, np.datetime64(pd.Timestamp(p["decision_date"]))))
        for j in (i - 252, i - 21, i, i + H_SHORT, i + H_LONG):
            if 0 <= j < len(cal):
                need.add(pd.Timestamp(cal[j]))
    syms = {p["symbol"] for p in packets}
    # the case's own symbol on every date, the cross-section on the dates the
    # median-stock and momentum benchmarks need
    bars_all = allb[allb["symbol"].isin(syms) | allb["date"].isin(need)]
    del allb
    oc = outcomes_for(packets, bars_all.sort_values(["symbol", "date"]))
    okey = {k: r for k, r in zip(oc["key"], oc.to_dict("records"))}
    rows = []
    for f in sorted((rd / "rows").glob("*.jsonl")):
        if f.name.endswith("_raw_local.jsonl"):
            continue
        rows += [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    R = pd.DataFrame(rows)
    receipt: dict = {"experiment": "AMNESIA-2 / fiction backtest, model-agnostic", "run": run,
                     "licence": "PRODUCT_EXPERIMENT (no claim)",
                     "generated_at": datetime.now(timezone.utc).isoformat(),
                     "registration": plan["registration"], "registration_sha256": plan["registration_sha256"],
                     "amnesia_vendored": {"path": plan["amnesia_vendored_from"], "sha256": plan["amnesia_sha256"]},
                     "rule": RULE, "sample_sizes": plan["sample_sizes"],
                     "leak_refusals_in_plan": len(plan["leak_refusals"]),
                     "dropped_headlines_in_plan": plan["dropped_headlines"],
                     "arm_cutoffs": ARM_CUTOFFS, "august_amnesia_1": AUGUST_TABLE, "cells": {},
                     "canaries": {}, "parse": {},
                     "outcomes_matured": {"r5": int(oc["r5"].notna().sum()), "r21": int(oc["r21"].notna().sum()),
                                          "n": int(len(oc))}}
    if not R.empty:
        for (arm, kind), g in R.groupby(["arm", "kind"]):
            receipt["parse"][f"{arm}|{kind}"] = {
                "n": int(len(g)), "parsed": int(g["parsed_ok"].sum()),
                "refusals": g.loc[~g["parsed_ok"], "refusal"].value_counts().to_dict(),
                "served_models": g["model_served"].fillna("None").value_counts().to_dict(),
                "cost_usd": float(pd.to_numeric(g["cost_usd"], errors="coerce").fillna(0).sum())}
        can = R[R["kind"] == "canary"]
        receipt["canaries"] = canary_table(can, cases) if len(can) else {}
        fc = R[(R["kind"] == "forecast") & R["parsed_ok"]]
        flat = []
        for _, r in fc.iterrows():
            o = okey.get(cases[r["case_id"]]["key"])
            if o is None:
                continue
            a = r["answer"]
            flat.append({"arm": r["arm"], "level": r["level"], "part": r["part"], "case_id": r["case_id"],
                         **o, **{k: a[k] for k in ("p_beat_median_5d", "p_beat_median_21d", "central_5d_pct",
                                                   "low80_5d_pct", "high80_5d_pct")},
                         "scenarios": a["scenarios"], "features": a["features"]})
        F = pd.DataFrame(flat)
        if len(F):
            for (arm, part, level), g in F.groupby(["arm", "part", "level"]):
                cell = grade_cell(g.reset_index(drop=True))
                cell["verdicts"] = verdicts(cell)
                receipt["cells"][f"{arm}|{part}|{level}"] = cell
            receipt["leak_test"] = leak_table(F, receipt["canaries"])
            n_by = F[F["part"] == "clean"].groupby(["arm", "level"]).size()
            receipt["mde_note"] = {f"{a}|{lv}": {"n": int(n),
                                                 "row_mde80_pp": round(2.8 * math.sqrt(0.25 / n) * 100, 1)}
                                   for (a, lv), n in n_by.items()}
    DG.atomic_write_json(rd / "receipt_analyze.json", receipt)
    print(json.dumps({"parse": receipt["parse"], "canaries": receipt["canaries"],
                      "leak_test": receipt.get("leak_test"), "matured": receipt["outcomes_matured"]},
                     indent=1, default=str))
    for k, c in receipt["cells"].items():
        d5 = c.get("dir5", {})
        r5 = c.get("range5", {})
        print(k, "n", c["n"], "hit5", round(d5.get("hit", float("nan")), 3),
              [round(x, 3) for x in d5.get("wilson95", (float("nan"),) * 2)],
              "mom", d5.get("momentum_hit_same_rows"), "brier", round(d5.get("brier", float("nan")), 4),
              "IS m/v", round(r5.get("interval_score_model", float("nan")), 2),
              round(r5.get("interval_score_vol_prior", float("nan")), 2), c["verdicts"])
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["plan", "probe-nvidia", "run", "ingest", "analyze", "amend"])
    ap.add_argument("--run", required=True)
    ap.add_argument("--part", default="clean")
    ap.add_argument("--arm", default="deepseek")
    ap.add_argument("--levels", default=",".join(LEVELS))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--model", default=None)
    ap.add_argument("--model-id", default=None)
    ap.add_argument("--allow-local", action="store_true")
    ap.add_argument("--kinds", default="canary,forecast")
    a = ap.parse_args(argv)
    from backend.services import disk_guard as DG                      # noqa: PLC0415
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    DG.require_free(20.0, "fiction_backtest", path=RUN_ROOT)
    if a.stage == "plan":
        stage_plan(a.run, a.part)
    elif a.stage == "probe-nvidia":
        stage_probe_nvidia(a.run, a.model)
    elif a.stage == "run":
        stage_run(a.run, a.arm, a.part.split(","), a.levels.split(","), a.limit, a.workers,
                  a.model_id, a.allow_local, tuple(a.kinds.split(",")))
    elif a.stage == "ingest":
        stage_ingest(a.run, a.arm, a.model_id)
    elif a.stage == "amend":
        stage_amend(a.run)
    else:
        stage_analyze(a.run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
