"""Thesis cards -- one structured analysis per chosen stock.

Murat, 2026-09-25: *"with all the stocks chosen run a stock analysis, run
openclaw for doing web scraping about it, get its analyst reviews and news and
upcoming dates, market strategy, demand, all the review."*

A card is three parts, kept separable so each can be graded on its own:

    engine side   what is ON DISK at `asof`: prices, the SEC quarter, the dated
                  analyst-revision flow, the news corpus, the catalyst YAML, the
                  latest investigator forecast. Pure, PIT-strict, every key
                  present (None = unavailable, never silently omitted).
    web side      ONE `openclaw agent` quest: the ten fixed questions + every
                  analyst action in 90 days + every dated IR event, returned as
                  FLAT JSON (nested objects broke 55% of parses on 09-24).
    synthesis     ONE DeepSeek call through `llm_analyzer` (the only LLM path;
                  language pin + telemetry inherited) that merges the two into
                  bull / bear / falsifier / verdict / confidence, told the
                  standing findings so it does not re-derive them.

WHAT A CARD IS NOT. It is evidence and a falsifier, not an order. A verdict of
`supports` is a statement about the evidence gathered, not a position size, and
nothing reads it as one.

REFUSALS ARE CARDS. An empty OpenClaw log produces a `REFUSED_EMPTY_LOG` card
with the engine side filled, never a silent skip -- the 09-24 power-bottleneck
quest left a 0-byte log and nothing on disk distinguished "never ran" from "ran
and found nothing".
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

# ─────────────────────────────── the schema ─────────────────────────────────

ENGINE_KEYS: tuple[str, ...] = (
    "engine_px", "engine_mom_21", "engine_mom_63", "engine_vol_63",
    "engine_band", "engine_cost_bps",
    "engine_rev_qoq", "engine_gross_margin", "engine_gross_margin_chg",
    "engine_inflection_flag",
    "engine_net_raises_90d", "engine_n_firms_90d",
    "engine_median_target_change_90d",
    "engine_forecast_p_up_1d", "engine_forecast_p_up_5d",
)

#: The ten fixed questions (Murat's review list, 2026-09-25 amendment).
TEN_QUESTIONS: tuple[str, ...] = (
    "What changed in the last 90 days?",
    "What is known today that was not known yesterday?",
    "Is growth coming from demand, price, volume or mix?",
    "Who are the key suppliers and are they constrained?",
    "Who are the key customers and how concentrated are they?",
    "Who loses if this company wins?",
    "What evidence CONTRADICTS the bull case?",
    "If management is right, what happens next?",
    "If management is wrong, what breaks first?",
    "Who are the second- and third-order beneficiaries?",
)

#: The flat keys the web quest must return. Lists hold plain strings only.
WEB_STR_KEYS: tuple[str, ...] = (
    "name", "what_changed", "not_known_yesterday", "demand_price_volume_mix",
    "suppliers", "customers", "who_loses", "contradicting_evidence",
    "if_management_right", "if_management_wrong", "second_order_beneficiaries",
    "product", "demand", "pricing_power", "competition", "team",
    "market_strategy", "consensus_source",
)
WEB_NUM_KEYS: tuple[str, ...] = ("consensus_n", "consensus_mean_target")
WEB_LIST_KEYS: tuple[str, ...] = ("analyst_actions", "upcoming_dates", "sources")
WEB_KEYS: tuple[str, ...] = WEB_STR_KEYS + WEB_NUM_KEYS + WEB_LIST_KEYS

SYNTH_KEYS: tuple[str, ...] = ("bull", "bear", "falsifier", "verdict", "confidence")
VERDICTS = ("supports", "neutral", "against")
CONFIDENCES = ("low", "med", "high")
KINDS = ("personal", "competition", "holding")

#: The card, exactly as specified in the amendment (order preserved).
CARD_KEYS: tuple[str, ...] = (
    "ticker", "name", "asof", "kind",
    *ENGINE_KEYS,
    "news_30d_count", "news_30d_top",
    "analyst_actions",
    "consensus_n", "consensus_mean_target", "consensus_implied_upside",
    "consensus_source",
    "upcoming_dates",
    "product", "demand", "pricing_power", "competition", "team",
    "market_strategy",
    "bull", "bear", "falsifier", "verdict", "confidence",
    "sources", "openclaw_log_path", "openclaw_elapsed_s", "deepseek_cost_usd",
    "card_hash",
)
_LIST_CARD_KEYS = ("news_30d_top", "analyst_actions", "upcoming_dates", "sources")
_NUM_CARD_KEYS = (*[k for k in ENGINE_KEYS if k not in ("engine_band",
                                                         "engine_inflection_flag")],
                  "news_30d_count", "consensus_n", "consensus_mean_target",
                  "consensus_implied_upside", "openclaw_elapsed_s",
                  "deepseek_cost_usd")
_LIST_CAPS = {"news_30d_top": 8, "analyst_actions": 10}

SCHEMA_VERSION = "thesis_card/v1"


def _cfg(name: str, default: Any) -> Any:
    try:
        from backend import config as C
        return getattr(C, name, default)
    except Exception:                                              # noqa: BLE001
        return default


SYNTH_PURPOSE = _cfg("THESIS_CARD_SYNTH_PURPOSE", "thesis_card_synth")
QUEST_PURPOSE = _cfg("THESIS_CARD_QUEST_PURPOSE", "thesis_card_quest")
NEWS_DAYS = int(_cfg("THESIS_CARD_NEWS_DAYS", 30))
REVISION_DAYS = int(_cfg("THESIS_CARD_REVISION_DAYS", 90))


def cards_root() -> Path:
    from backend import config as C
    return Path(C.OPTIMUS_LEDGER_DIR) / _cfg("THESIS_CARD_SUBDIR", "thesis_cards")


# ─────────────────────────────── helpers ────────────────────────────────────

def _num(v: Any, nd: int = 4) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(f) else round(f, nd)


def _asof_date(asof: Any) -> date:
    if isinstance(asof, datetime):
        return asof.date()
    if isinstance(asof, date):
        return asof
    return date.fromisoformat(str(asof)[:10])


def _day(v: Any) -> str | None:
    s = str(v or "")[:10]
    try:
        date.fromisoformat(s)
    except ValueError:
        return None
    return s


def _clean(s: Any, n: int = 160) -> str:
    return re.sub(r"\s+", " ", str(s if s is not None else "")).replace("|", "/").strip()[:n]


# ─────────────────────────────── engine side ────────────────────────────────

def _bars_part(ticker: str, asof_d: date, bars) -> dict:
    out = {k: None for k in ("engine_px", "engine_mom_21", "engine_mom_63",
                             "engine_vol_63", "engine_band", "engine_cost_bps")}
    if bars is None:
        return out
    import numpy as np
    import pandas as pd
    b = bars[bars["symbol"] == ticker]
    if b.empty:
        return out
    b = b[pd.to_datetime(b["date"]) <= pd.Timestamp(asof_d)].sort_values("date")
    if b.empty:
        return out
    c = b["close"].astype(float).to_numpy()
    out["engine_px"] = _num(c[-1], 4)
    if len(c) > 21 and c[-22] > 0:
        out["engine_mom_21"] = _num(c[-1] / c[-22] - 1)
    if len(c) > 63 and c[-64] > 0:
        out["engine_mom_63"] = _num(c[-1] / c[-64] - 1)
        lr = np.diff(np.log(c[-64:]))
        out["engine_vol_63"] = _num(float(np.std(lr, ddof=1)) * math.sqrt(252))
    if "volume" in b.columns:
        dv = (b["close"].astype(float) * b["volume"].astype(float)).tail(63)
        mdv = float(dv.median()) if len(dv) else float("nan")
        if math.isfinite(mdv):
            from backend.services import xs_ranker as XR
            out["engine_band"] = XR.liquidity_band(mdv)
            out["engine_cost_bps"] = _num(XR.round_trip_bps(mdv), 1)
    return out


def _revisions_part(ticker: str, asof_d: date, revisions) -> tuple[dict, list[str] | None]:
    out = {"engine_net_raises_90d": None, "engine_n_firms_90d": None,
           "engine_median_target_change_90d": None}
    if revisions is None:
        return out, None
    import pandas as pd
    d = revisions[revisions["ticker"] == ticker]
    if d.empty:
        return out, []
    if "pit_safe" in d.columns:
        d = d[d["pit_safe"].astype(bool)]
    ts = pd.to_datetime(d["event_date"], errors="coerce", utc=True)
    end = pd.Timestamp(asof_d, tz="UTC") + pd.Timedelta(days=1)   # end of asof day
    start = end - pd.Timedelta(days=REVISION_DAYS + 1)
    d = d.assign(evt_ts=ts)[(ts < end) & (ts >= start)]
    if d.empty:
        return out, []
    ta = d["target_action"].astype(str).str.lower()
    out["engine_net_raises_90d"] = int((ta == "raises").sum() - (ta == "lowers").sum())
    out["engine_n_firms_90d"] = int(d["firm"].nunique())
    tc = pd.to_numeric(d["target_change"], errors="coerce")
    tc = tc[tc.abs() < 10]          # initiations carry prior 0 -> inf; not a change
    out["engine_median_target_change_90d"] = _num(tc.median()) if len(tc) else None
    acts = []
    for r in d.sort_values("evt_ts", ascending=False).itertuples():
        fg, tg = _clean(getattr(r, "from_grade", ""), 30), _clean(getattr(r, "to_grade", ""), 30)
        pt, ct = _num(getattr(r, "prior_target", None), 2), _num(getattr(r, "current_target", None), 2)
        if pt is not None or ct is not None:
            move = f"{pt if pt else 'new'}->{ct}"
        else:
            move = f"{fg or 'new'}->{tg}"
        acts.append(f"{str(r.evt_ts)[:10]} | {_clean(r.firm, 40)} | "
                    f"{_clean(r.target_action, 20).lower()} {tg}".rstrip()
                    + f" | {move}")
    return out, acts


def _news_part(ticker: str, asof_d: date, news_rows) -> dict:
    if news_rows is None:
        return {"news_30d_count": None, "news_30d_top": None}
    lo = asof_d - timedelta(days=NEWS_DAYS)
    seen: dict[str, tuple] = {}
    for r in news_rows:
        if ticker not in (r.get("tickers") or []):
            continue
        d = _day(r.get("published_utc") or r.get("first_seen_utc"))
        if d is None:
            continue
        dd = date.fromisoformat(d)
        if dd > asof_d or dd < lo:
            continue
        key = (r.get("url") or "").strip() or _clean(r.get("title"), 200).lower()
        stamp = str(r.get("published_utc") or r.get("first_seen_utc"))
        if key in seen and seen[key][0] >= stamp:
            continue
        seen[key] = (stamp, d, _clean(r.get("source"), 40),
                     _clean(r.get("title"), 160), (r.get("url") or "").strip())
    rows = sorted(seen.values(), key=lambda x: x[0], reverse=True)
    return {"news_30d_count": len(rows),
            "news_30d_top": [f"{d} | {s} | {t} | {u}" for _, d, s, t, u in rows[:8]]}


def _catalysts_part(ticker: str, asof_d: date, catalysts) -> list[str] | None:
    if catalysts is None:
        return None
    out = []
    for c in catalysts:
        if str(c.get("ticker", "")).upper() != ticker.upper():
            continue
        d = _day(c.get("date"))
        if d is None or date.fromisoformat(d) < asof_d:
            continue
        out.append((d, f"{d} | {_clean(c.get('kind'), 30)} | {_clean(c.get('what'), 120)} | "
                       f"{(c.get('source_url') or '').strip()} | "
                       f"{_clean(c.get('verified_from') or 'unverified', 20)}"))
    return [s for _, s in sorted(out)]


def _forecast_part(ticker: str, asof_d: date, predictions) -> dict:
    out = {"engine_forecast_p_up_1d": None, "engine_forecast_p_up_5d": None}
    if predictions is None:
        return out
    cutoff = (asof_d + timedelta(days=1)).isoformat()
    best: dict[int, tuple[str, float]] = {}
    for p in predictions:
        if p.get("ticker") != ticker:
            continue
        if not str(p.get("specialist", "")).startswith("investigator:"):
            continue
        h = p.get("horizon_days")
        made = str(p.get("made_at") or "")
        if h not in (1, 5) or not made or made >= cutoff:
            continue
        pr = _num(p.get("probability"))
        if pr is None:
            continue
        if h not in best or made > best[h][0]:
            best[h] = (made, pr)
    if 1 in best:
        out["engine_forecast_p_up_1d"] = best[1][1]
    if 5 in best:
        out["engine_forecast_p_up_5d"] = best[5][1]
    return out


def engine_side(ticker: str, *, asof: Any, bars=None, revisions=None,
                news_rows: Iterable[dict] | None = None,
                catalysts: Iterable[dict] | None = None,
                predictions: Iterable[dict] | None = None,
                fundamentals: dict | None = None) -> dict:
    """Everything on disk about `ticker` that was knowable at `asof`.

    Pure: every input is passed in. `None` for an input means UNAVAILABLE and
    every key it feeds is None, listed in `engine_unavailable`; an empty list
    means MEASURED and yields zeros where a count is asked (a quiet name is not
    an unknown one). Rows dated after `asof` are never read.
    """
    t = str(ticker).upper()
    a = _asof_date(asof)
    unavailable = []
    news_rows = list(news_rows) if news_rows is not None else None
    catalysts = list(catalysts) if catalysts is not None else None
    predictions = list(predictions) if predictions is not None else None

    out: dict = {k: None for k in ENGINE_KEYS}
    bp = _bars_part(t, a, bars)
    out.update(bp)
    if bars is None:
        unavailable.append("bars")
    elif bp["engine_px"] is None:
        unavailable.append("bars:no_rows_for_ticker")

    f = fundamentals if fundamentals is not None else None
    if f:
        out["engine_rev_qoq"] = _num(f.get("rev_qoq"))
        out["engine_gross_margin"] = _num(f.get("gross_margin"))
        out["engine_gross_margin_chg"] = _num(f.get("gross_margin_chg"))
        fl = f.get("inflection_flag")
        out["engine_inflection_flag"] = None if fl is None else bool(fl)
    else:
        unavailable.append("fundamentals")

    rp, acts = _revisions_part(t, a, revisions)
    out.update(rp)
    if revisions is None:
        unavailable.append("revisions")
    out["engine_analyst_actions_90d"] = acts

    out.update(_news_part(t, a, news_rows))
    if news_rows is None:
        unavailable.append("news")

    out["engine_upcoming_dates"] = _catalysts_part(t, a, catalysts)
    if catalysts is None:
        unavailable.append("catalysts")

    out.update(_forecast_part(t, a, predictions))
    if predictions is None:
        unavailable.append("predictions")

    out["engine_unavailable"] = unavailable
    out["engine_asof"] = a.isoformat()
    out["engine_last_filed"] = (f or {}).get("last_filed")
    return out


# ─────────────────────────────── web side ───────────────────────────────────

SOURCE_POLICY = (
    "SOURCES, in order of trust: (1) the company's own investor relations site "
    "and press releases; (2) SEC / exchange filings and exchange notices; "
    "(3) major wires (Reuters, Bloomberg, AP, Dow Jones, PR Newswire, Business "
    "Wire, GlobeNewswire, Nikkei, Yonhap). Blogs, forums, Reddit, X and "
    "aggregator sites are CONTEXT ONLY: never the sole source for a number, "
    "a date or an analyst action. Mark every dated event `primary` if you read "
    "it on (1) or (2), else `aggregator`. Do not log in, fill forms, pay, or "
    "accept any paywall. If a page will not load, say so and move on.")


def quest_prompt(ticker: str, engine: dict) -> str:
    """The ONE OpenClaw quest for a ticker. Tells the agent what the engine
    already knows so it spends its browsing on the gaps."""
    known = {k: engine.get(k) for k in (
        "engine_px", "engine_band", "engine_mom_63", "engine_net_raises_90d",
        "engine_n_firms_90d", "news_30d_count")}
    known["engine_upcoming_dates"] = engine.get("engine_upcoming_dates")
    keys_shape = {k: ("" if k in WEB_STR_KEYS else 0 if k in WEB_NUM_KEYS else [])
                  for k in WEB_KEYS}
    suffix_note = ""
    if "." in ticker:
        suffix_note = ("\nThis is a NON-US listing (Yahoo/Bloomberg suffix). Read the "
                       "company's investor relations page in ENGLISH where one exists; "
                       "report prices and targets in the listing currency and say which.\n")
    qs = "\n".join(f"{i}. {q}" for i, q in enumerate(TEN_QUESTIONS, 1))
    return f"""You are gathering EVIDENCE about ONE company, ticker {ticker}. You are
not asked whether to buy it; an opinion without a source is discarded.
Use your browser / web tools. Today is {engine.get("engine_asof") or date.today().isoformat()}.
{suffix_note}
WHAT THE ENGINE ALREADY KNOWS (do not re-derive; fill the gaps):
{json.dumps(known, default=str)}

{SOURCE_POLICY}

ANSWER THESE TEN QUESTIONS, each in at most 60 words, each with a date where
one exists. If you found nothing, write "not found" -- never guess:
{qs}

ALSO:
A. List EVERY analyst action in the last 90 days you can find (rating change,
   initiation, price-target change), each as the plain string
   "YYYY-MM-DD | firm | action | from->to". At most 10, newest first.
B. List EVERY dated upcoming event from the company's investor relations page
   (earnings date, investor day, FDA/PDUFA date, product launch, shareholder
   meeting, lockup expiry), each as the plain string
   "YYYY-MM-DD | kind | what | source_url | primary|aggregator".
C. Consensus: number of analysts (consensus_n), mean price target
   (consensus_mean_target, a number), and the URL you read it on (consensus_source).
D. product, demand, pricing_power, competition, team, market_strategy: one or
   two plain sentences each, from what you read.
E. sources: every URL you actually read.

Return FLAT JSON ONLY, nothing before or after it, exactly these keys. Every
value is a plain string, a number, null, or a list of plain strings. NO nested
objects, no quotation marks inside strings, no newlines inside strings:
{json.dumps(keys_shape)}

Map the ten questions to: what_changed, not_known_yesterday,
demand_price_volume_mix, suppliers, customers, who_loses,
contradicting_evidence, if_management_right, if_management_wrong,
second_order_beneficiaries. contradicting_evidence is NOT optional: a report
with no disconfirming evidence is incomplete.
"""


def _empty_web() -> dict:
    return {k: None for k in WEB_KEYS}


def parse_reply(text: str | None, *, keys: tuple[str, ...] = WEB_KEYS) -> dict:
    """The agent's FLAT JSON -> the known keys, or a DEGRADED lift, or a refusal.

    Every key in `keys` is present in the result. Unknown keys are DROPPED and
    named (`parse_dropped_keys`); nested objects are REJECTED to None and named
    (`parse_rejected_nested`) -- a flat schema that silently accepts nesting is
    how 55% of 09-24's parses broke. On a JSON error only the scalar strings,
    numbers and plain-string lists that can be read unambiguously are lifted;
    everything else is None. Nothing is repaired and nothing is guessed.
    """
    out: dict = {k: None for k in keys}
    txt = (text or "").strip()
    if "{" not in txt or "}" not in txt:
        out.update(parse="refused", parse_error="no JSON object in reply",
                   raw_head=txt[:300])
        return out
    blob = txt[txt.index("{"):txt.rindex("}") + 1]
    try:
        d = json.loads(blob)
        if not isinstance(d, dict):
            raise ValueError("top level is not an object")
    except ValueError as exc:
        out["parse"] = "degraded"
        out["parse_error"] = str(exc)[:160]
        for k in keys:
            m = re.search(r'"' + re.escape(k) + r'"\s*:\s*(-?\d+(?:\.\d+)?)\s*[,}]', blob)
            if m:
                v = float(m.group(1))
                out[k] = int(v) if v.is_integer() and k == "consensus_n" else v
                continue
            # a string whose closing quote is followed by , or } -- anything else
            # means an unescaped quote inside, and that value is not lifted
            m = re.search(r'"' + re.escape(k) + r'"\s*:\s*"([^"\\]*)"\s*[,}]', blob)
            if m:
                out[k] = m.group(1)
                continue
            m = re.search(r'"' + re.escape(k) + r'"\s*:\s*(\[[^\[\]]*\])', blob)
            if m:
                try:
                    lst = json.loads(m.group(1))
                    if all(isinstance(x, str) for x in lst):
                        out[k] = lst
                except ValueError:
                    pass
        if not any(out[k] is not None for k in keys):
            out["parse"] = "refused"
        return out

    dropped = sorted(k for k in d if k not in keys)
    nested = []
    for k in keys:
        if k not in d:
            continue
        v = d[k]
        if isinstance(v, dict):
            nested.append(k)
            continue
        if isinstance(v, list):
            if not all(isinstance(x, (str, int, float)) for x in v):
                nested.append(k)
                continue
            v = [str(x) for x in v]
        out[k] = v
    out["parse"] = "ok"
    if dropped:
        out["parse_dropped_keys"] = dropped
    if nested:
        out["parse_rejected_nested"] = nested
    return out


# ─────────────────────────────── synthesis ──────────────────────────────────

STANDING = (
    "§17 analyst price-target LEVELS are CLOSED/PERVERSE (t -3.6): a large "
    "implied upside to the mean target is NOT a reason to buy; dated revisions "
    "(raises vs lowers) are different and still carry information",
    "§59 price/volume alone cannot rank this cross-section at 21 sessions; "
    "momentum is context, not a thesis",
    "§63 revenue growth with margin expansion has NO dose-response: an "
    "inflection flag alone does not support a verdict",
    "§64 process beats persona: facts with named sources and a falsifier; "
    "confident calls on weak evidence were the failure mode (skill is at 1 day, "
    "gone by 5)",
)

SYNTH_SYSTEM = (
    "You merge an ENGINE record (on-disk data) and a WEB record (one browsing "
    "quest) about one company into a thesis card. You are not placing a trade.\n"
    "STANDING RESULTS, already settled -- do not re-derive or contradict them:\n"
    + "\n".join(f"- {s}" for s in STANDING)
    + "\nRules: use only the two records; null means unknown. The falsifier must "
    "be ONE observable event with a date or a number that would prove the bull "
    "case wrong. verdict is one of supports|neutral|against (about the evidence, "
    "not a price call); confidence is one of low|med|high, and high needs dated "
    "primary-source evidence. Keep bull, bear and falsifier under 50 words each.\n"
    "Return FLAT JSON ONLY, nothing before or after, plain strings, no nesting:\n"
    '{"bull": "", "bear": "", "falsifier": "", "verdict": "neutral", '
    '"confidence": "low"}'
)

_SYNTH_WEB_FIELDS = tuple(k for k in WEB_KEYS if k != "sources")


def synth_user(engine: dict, web: dict) -> str:
    eng = {k: engine.get(k) for k in (*ENGINE_KEYS, "news_30d_count",
                                       "engine_upcoming_dates")}
    eng["engine_last_filed"] = engine.get("engine_last_filed")
    eng["news_30d_top"] = (engine.get("news_30d_top") or [])[:5]
    eng["engine_analyst_actions_90d"] = (engine.get("engine_analyst_actions_90d") or [])[:6]
    w = {}
    for k in _SYNTH_WEB_FIELDS:
        v = (web or {}).get(k)
        if isinstance(v, str):
            v = v[:500]
        elif isinstance(v, list):
            v = [str(x)[:200] for x in v[:10]]
        w[k] = v
    w["web_parse"] = (web or {}).get("parse")
    return ("ENGINE RECORD:\n" + json.dumps(eng, default=str)
            + "\n\nWEB RECORD:\n" + json.dumps(w, default=str))


def synthesize(engine: dict, web: dict, *, model: str,
               call_fn: Callable[..., str | None] | None = None) -> dict:
    """One DeepSeek call via `llm_analyzer._call_llm` -> bull/bear/falsifier/
    verdict/confidence, plus `synth_status`.

    `model` is RECORDED: `llm_analyzer` owns model choice (the single DeepSeek
    path, language pin, telemetry), and the model it actually used is stamped as
    `synth_model` beside the one requested so a mismatch is visible, not assumed
    away. Out-of-vocabulary verdict/confidence become None with status
    `INVALID_VOCAB` -- never coerced to the nearest word.
    """
    used = model
    if call_fn is None:
        from backend.services import llm_analyzer as LA
        call_fn = LA._call_llm
        used = getattr(LA, "_DEEPSEEK_MODEL", model)
    txt = call_fn(SYNTH_SYSTEM, synth_user(engine or {}, web or {}),
                  purpose=SYNTH_PURPOSE,
                  validate=lambda t: parse_reply(t, keys=SYNTH_KEYS).get("parse") == "ok")
    out = {k: None for k in SYNTH_KEYS}
    out.update(synth_model_requested=model, synth_model=used)
    if not txt:
        out["synth_status"] = "NO_REPLY"
        return out
    p = parse_reply(txt, keys=SYNTH_KEYS)
    for k in SYNTH_KEYS:
        v = p.get(k)
        out[k] = v if isinstance(v, str) or v is None else str(v)
    status = "OK" if p.get("parse") == "ok" else f"PARSE_{str(p.get('parse')).upper()}"
    v = (out["verdict"] or "").strip().lower()
    c = (out["confidence"] or "").strip().lower()
    c = {"medium": "med"}.get(c, c)
    bad = False
    out["verdict"] = v if v in VERDICTS else None
    out["confidence"] = c if c in CONFIDENCES else None
    if (v and v not in VERDICTS) or (c and c not in CONFIDENCES):
        bad = True
    if bad and status == "OK":
        status = "INVALID_VOCAB"
    out["synth_status"] = status
    if status != "OK":
        out["synth_raw_head"] = txt[:300]
    return out


# ─────────────────────────────── the card ───────────────────────────────────

def card_hash(card: dict) -> str:
    """sha256 over every field except the hash itself (and private `_` keys)."""
    body = {k: v for k, v in card.items() if k != "card_hash" and not k.startswith("_")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str)
                          .encode("utf-8")).hexdigest()[:16]


def _merge_lists(*lists: Iterable[str] | None, cap: int | None = None) -> list[str]:
    seen, out = set(), []
    for lst in lists:
        for x in lst or []:
            s = str(x).strip()
            key = re.sub(r"\s+", " ", s.lower())
            if s and key not in seen:
                seen.add(key)
                out.append(s)
    return out[:cap] if cap else out


def _by_date(items: list[str], *, reverse: bool) -> list[str]:
    def k(s):
        return _day(s.split("|")[0].strip()) or ("0000" if reverse else "9999")
    return sorted(items, key=k, reverse=reverse)


def build_card(ticker: str, *, kind: str, asof: Any, engine: dict, web: dict,
               synth: dict, meta: dict | None = None) -> dict:
    """Engine + web + synthesis -> the flat card, hashed."""
    meta = meta or {}
    web = web or {}
    synth = synth or {}
    c: dict = {"ticker": str(ticker).upper(), "name": web.get("name"),
               "asof": _asof_date(asof).isoformat(), "kind": kind}
    for k in ENGINE_KEYS:
        c[k] = engine.get(k)
    c["news_30d_count"] = engine.get("news_30d_count")
    c["news_30d_top"] = engine.get("news_30d_top")
    acts = _merge_lists(engine.get("engine_analyst_actions_90d"),
                        web.get("analyst_actions"))
    c["analyst_actions"] = _by_date(acts, reverse=True)[:10]
    n = web.get("consensus_n")
    c["consensus_n"] = int(n) if _num(n) is not None else None
    c["consensus_mean_target"] = _num(web.get("consensus_mean_target"), 4)
    px = c.get("engine_px")
    c["consensus_implied_upside"] = (
        _num(c["consensus_mean_target"] / px - 1)
        if c["consensus_mean_target"] and px else None)
    c["consensus_source"] = web.get("consensus_source")
    c["upcoming_dates"] = _by_date(_merge_lists(engine.get("engine_upcoming_dates"),
                                                web.get("upcoming_dates")),
                                   reverse=False)
    for k in ("product", "demand", "pricing_power", "competition", "team",
              "market_strategy"):
        c[k] = web.get(k)
    for k in SYNTH_KEYS:
        c[k] = synth.get(k)
    cat_urls = [s.split("|")[3].strip() for s in (engine.get("engine_upcoming_dates") or [])
                if len(s.split("|")) > 3 and s.split("|")[3].strip()]
    c["sources"] = _merge_lists(web.get("sources"), cat_urls)
    c["openclaw_log_path"] = meta.get("openclaw_log_path")
    c["openclaw_elapsed_s"] = _num(meta.get("openclaw_elapsed_s"), 2)
    c["deepseek_cost_usd"] = _num(meta.get("deepseek_cost_usd"), 6)
    # ── beyond the spec: the ten answers and provenance, flat ──
    for k in ("what_changed", "not_known_yesterday", "demand_price_volume_mix",
              "suppliers", "customers", "who_loses", "contradicting_evidence",
              "if_management_right", "if_management_wrong",
              "second_order_beneficiaries"):
        c[f"web_{k}"] = web.get(k)
    c["web_parse"] = web.get("parse")
    c["synth_status"] = synth.get("synth_status")
    c["synth_model"] = synth.get("synth_model")
    c["engine_unavailable"] = engine.get("engine_unavailable")
    c["engine_last_filed"] = engine.get("engine_last_filed")
    for k in ("openclaw_status", "openclaw_cost_usd", "quest_model", "source"):
        if k in meta:
            c[k] = meta[k]
    c["schema"] = SCHEMA_VERSION
    c["card_hash"] = card_hash(c)
    return c


def refusal_card(ticker: str, *, kind: str, asof: Any, engine: dict,
                 verdict: str, why: str, meta: dict | None = None) -> dict:
    """A card that says the web side failed, with the engine side intact."""
    if not str(verdict).startswith("REFUSED_"):
        raise ValueError(f"a refusal verdict must start with REFUSED_: {verdict!r}")
    c = build_card(ticker, kind=kind, asof=asof, engine=engine, web=_empty_web(),
                   synth={"synth_status": "NOT_RUN"}, meta=meta)
    c["verdict"] = verdict
    c["refusal_why"] = str(why)[:400]
    c["card_hash"] = card_hash(c)
    return c


def validate_card(card: dict) -> list[str]:
    """Every way a card departs from the schema. READS ONLY -- a seed card that
    drifted is reported, never rewritten."""
    probs: list[str] = []
    if not isinstance(card, dict):
        return ["card is not an object"]
    for k in CARD_KEYS:
        if k not in card:
            probs.append(f"missing key: {k}")
    t = card.get("ticker")
    if not isinstance(t, str) or not t or t != t.upper():
        probs.append(f"ticker not an upper-case string: {t!r}")
    if "asof" in card and _day(card.get("asof")) is None:
        probs.append(f"asof not YYYY-MM-DD: {card.get('asof')!r}")
    if "kind" in card and card.get("kind") not in KINDS:
        probs.append(f"kind {card.get('kind')!r} not in {KINDS}")
    v = card.get("verdict")
    if "verdict" in card and not (v in VERDICTS or (isinstance(v, str)
                                                    and v.startswith("REFUSED_"))):
        probs.append(f"verdict {v!r} not in {VERDICTS} or REFUSED_*")
    c = card.get("confidence")
    if "confidence" in card and c is not None and c not in CONFIDENCES:
        probs.append(f"confidence {c!r} not in {CONFIDENCES}")
    for k in _LIST_CARD_KEYS:
        val = card.get(k)
        if k in card and val is not None:
            if not isinstance(val, list):
                probs.append(f"{k} is {type(val).__name__}, not a list")
            elif not all(isinstance(x, str) for x in val):
                probs.append(f"{k} holds non-string items (nested objects are refused)")
            elif k in _LIST_CAPS and len(val) > _LIST_CAPS[k]:
                probs.append(f"{k} has {len(val)} items > cap {_LIST_CAPS[k]}")
    for k in _NUM_CARD_KEYS:
        val = card.get(k)
        if k in card and val is not None and (isinstance(val, bool)
                                              or not isinstance(val, (int, float))):
            probs.append(f"{k} is {type(val).__name__}, not a number or null")
    for k in CARD_KEYS:
        if isinstance(card.get(k), dict):
            probs.append(f"{k} is a nested object")
    h = card.get("card_hash")
    if h and h != card_hash(card):
        probs.append("card_hash mismatch: content changed after hashing "
                     "(or a different hash recipe)")
    return probs


def _safe_name(ticker: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(ticker).upper())


def card_path(ticker: str, asof: Any, *, root: Path | None = None) -> Path:
    r = Path(root) if root is not None else cards_root()
    return r / _asof_date(asof).isoformat() / f"{_safe_name(ticker)}.json"


def write_card(card: dict, *, root: Path | None = None) -> Path:
    p = card_path(card["ticker"], card["asof"], root=root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(card, indent=1, default=str, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(p)
    return p


def read_cards(day: Any, *, root: Path | None = None) -> list[dict]:
    """Every card for a date. An unreadable file is returned as
    `{"_unreadable": path, "_error": ...}` rather than skipped."""
    r = Path(root) if root is not None else cards_root()
    d = r / _asof_date(day).isoformat()
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        if p.name.startswith("_"):          # run receipts, not cards
            continue
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(c, dict):
                raise ValueError("not an object")
            out.append(c)
        except (OSError, ValueError) as exc:
            out.append({"_unreadable": str(p), "_error": str(exc)[:160]})
    return out


def write_digest(day: Any, *, root: Path | None = None) -> Path:
    """`<date>/DIGEST.md`: one line per card -- ticker | verdict | confidence |
    next date | falsifier. Rewritten whole, so it is always the folder's truth."""
    r = Path(root) if root is not None else cards_root()
    ds = _asof_date(day).isoformat()
    cards = read_cards(ds, root=r)
    lines = [f"# Thesis cards {ds}", "",
             f"{sum(1 for c in cards if not c.get('_unreadable'))} cards. "
             "A verdict is about the evidence gathered, not an order.", "",
             "| ticker | verdict | confidence | next date | falsifier |",
             "|---|---|---|---|---|"]
    for c in cards:
        if c.get("_unreadable"):
            lines.append(f"| {Path(c['_unreadable']).stem} | UNREADABLE | | | "
                         f"{_clean(c.get('_error'), 80)} |")
            continue
        ud = c.get("upcoming_dates") or []
        nxt = _clean(ud[0], 80) if isinstance(ud, list) and ud else ""
        lines.append(f"| {c.get('ticker')} | {c.get('verdict')} | {c.get('confidence')} "
                     f"| {nxt} | {_clean(c.get('falsifier'), 200)} |")
    p = r / ds / "DIGEST.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p
