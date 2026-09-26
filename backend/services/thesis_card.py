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

#: Murat's twelve questions (external_session_brief_2026-09-26 section F),
#: one FLAT reply key each, in his order. Replaced the ten of 2026-09-25 on
#: 2026-09-26 (schema thesis_card/v2); a v1 card's ten answers stay readable.
TWELVE_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("what_changed_30_90d", "What changed in the last 30 and in the last 90 days?"),
    ("true_now_not_modelled", "What is true NOW that analysts may not have modelled yet?"),
    ("demand_product", "What product creates the demand?"),
    ("price_volume_mix", "Is growth coming from price, volume or mix?"),
    ("bottleneck", "What is the bottleneck (the company's, or the one it relieves)?"),
    ("who_benefits_next", "Who benefits NEXT (second- and third-order beneficiaries)?"),
    ("who_loses", "Who loses if this company wins?"),
    ("margin_collapse_risk", "What would collapse margins?"),
    ("low_cost_substitute", "Is there a Chinese or other low-cost substitute, and how close is it?"),
    ("ceo_promised", "What did the CEO / management PROMISE (dated, quoted)?"),
    ("did_they_deliver", "Did they deliver on earlier promises (dated evidence)?"),
    ("what_would_falsify", "What observable event, with a date or a number, would falsify the thesis?"),
)
ANSWER_KEYS: tuple[str, ...] = tuple(k for k, _ in TWELVE_QUESTIONS)
QUESTIONS: tuple[str, ...] = tuple(q for _, q in TWELVE_QUESTIONS)
#: The v1 card's ten answer keys, kept so the digest can say a diff is across schemas.
V1_ANSWER_KEYS: tuple[str, ...] = (
    "what_changed", "not_known_yesterday", "demand_price_volume_mix", "suppliers",
    "customers", "who_loses", "contradicting_evidence", "if_management_right",
    "if_management_wrong", "second_order_beneficiaries")

#: The three X reads made INSIDE the same quest, plus the dated claim and
#: promise lists. Every item starts with YYYY-MM-DD; one that does not is moved
#: to `undated_claims` by `parse_reply` -- refused as evidence, never dropped.
X_LIST_KEYS: tuple[str, ...] = ("x_company_posts", "x_ceo_posts", "x_analyst_posts")
DATED_LIST_KEYS: tuple[str, ...] = (*X_LIST_KEYS, "claims", "promises")

#: The flat keys the web quest must return. Lists hold plain strings only.
WEB_STR_KEYS: tuple[str, ...] = ("name", *ANSWER_KEYS, "consensus_source")
WEB_NUM_KEYS: tuple[str, ...] = ("consensus_n", "consensus_mean_target")
WEB_LIST_KEYS: tuple[str, ...] = (*DATED_LIST_KEYS, "analyst_actions",
                                  "upcoming_dates", "sources")
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

SCHEMA_VERSION = "thesis_card/v2"


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


def _prior_card_brief(prior: dict | None) -> dict | None:
    """What the previous card of this name concluded -- so the quest asks what
    CHANGED since then instead of re-deriving it."""
    if not prior:
        return None
    out = {"asof": prior.get("asof"), "verdict": prior.get("verdict"),
           "falsifier": _clean(prior.get("falsifier"), 240)}
    for k in ANSWER_KEYS:
        v = prior.get(f"web_{k}")
        if v:
            out[k] = _clean(v, 160)
    return out


def quest_prompt(ticker: str, engine: dict, *, prior_card: dict | None = None,
                 open_promises: Iterable[dict] | None = None) -> str:
    """The ONE OpenClaw quest for a ticker: Murat's twelve questions plus two X
    reads, in the same turn. Tells the agent what the engine and the previous
    card already know (Murat: "use all of the files we have") so it spends its
    browsing on the gaps, and hands it the OPEN promises on file to grade."""
    known = {k: engine.get(k) for k in (
        "engine_px", "engine_band", "engine_mom_21", "engine_mom_63",
        "engine_vol_63", "engine_rev_qoq", "engine_gross_margin",
        "engine_net_raises_90d", "engine_n_firms_90d", "news_30d_count")}
    known["engine_upcoming_dates"] = engine.get("engine_upcoming_dates")
    known["engine_analyst_actions_90d"] = (engine.get("engine_analyst_actions_90d") or [])[:6]
    known["news_30d_top"] = (engine.get("news_30d_top") or [])[:5]
    keys_shape = {k: ("" if k in WEB_STR_KEYS else 0 if k in WEB_NUM_KEYS else [])
                  for k in WEB_KEYS}
    suffix_note = ""
    if "." in ticker:
        suffix_note = ("\nThis is a NON-US listing (Yahoo/Bloomberg suffix). Read the "
                       "company's investor relations page in ENGLISH where one exists; "
                       "report prices and targets in the listing currency and say which.\n")
    qs = "\n".join(f"{i}. [{k}] {q}" for i, (k, q) in enumerate(TWELVE_QUESTIONS, 1))
    prior = _prior_card_brief(prior_card)
    prior_txt = ("\nTHE PREVIOUS CARD ON THIS NAME (say what CHANGED since it; do not "
                 "repeat it):\n" + json.dumps(prior, default=str) + "\n") if prior else ""
    proms = [f"{p.get('promised_utc')} | due {p.get('due_utc') or 'none'} | "
             f"{p.get('promise_text')}" for p in (open_promises or [])][:10]
    prom_txt = ("\nOPEN PROMISES ON FILE -- for EACH, find dated evidence and return it "
                "in `promises` with the promise text COPIED EXACTLY and status "
                "DELIVERED, MISSED or still OPEN:\n" + "\n".join(proms) + "\n") if proms else ""
    today = engine.get("engine_asof") or date.today().isoformat()
    return f"""You are gathering EVIDENCE about ONE company, ticker {ticker}. You are
not asked whether to buy it; an opinion without a source is discarded.
Use your browser / web tools, and the logged-in X (x.com) account. Today is {today}.
{suffix_note}
WHAT THE ENGINE ALREADY KNOWS (do not re-derive; fill the gaps):
{json.dumps(known, default=str)}
{prior_txt}{prom_txt}
{SOURCE_POLICY}

ANSWER THESE TWELVE QUESTIONS, each in at most 60 words. EVERY factual claim
carries its date (YYYY-MM-DD) and source in the text. If you found nothing,
write "not found" -- never guess:
{qs}

X READS (open x.com; read, never post, like or follow):
X1. x_company_posts and x_ceo_posts: the company's own account and the CEO's
    own account, posts in the last 30 days. Each item is the plain string
    "YYYY-MM-DD | @handle | quoted text (at most 200 chars) | post URL".
X2. x_analyst_posts: sell-side analysts and industry accounts posting on this
    name in the last 30 days, same format. X is CONTEXT: it may raise a
    question, it never settles a number.

ALSO:
A. claims: every dated fact behind your twelve answers, each as the plain string
   "YYYY-MM-DD | question_key | source (@handle or site) | url | claim (at most 200 chars)".
   A claim you cannot date does not belong here.
B. promises: every dated management promise you found (and every OPEN promise
   on file), each as "YYYY-MM-DD promised | YYYY-MM-DD due or none |
   OPEN|DELIVERED|MISSED | the promise, quoted | dated evidence for the status".
C. analyst_actions: every analyst action in the last 90 days, each as
   "YYYY-MM-DD | firm | action | from->to". At most 10, newest first.
D. upcoming_dates: every dated upcoming event from the company's investor
   relations page, each as "YYYY-MM-DD | kind | what | source_url | primary|aggregator".
E. Consensus: number of analysts (consensus_n), mean price target
   (consensus_mean_target, a number), and the URL you read it on (consensus_source).
F. sources: every URL you actually read.

Return FLAT JSON ONLY, nothing before or after it, exactly these keys. Every
value is a plain string, a number, null, or a list of plain strings. NO nested
objects, no quotation marks inside strings, no newlines inside strings:
{json.dumps(keys_shape)}

The twelve answers go in the keys named in brackets above. what_would_falsify
is NOT optional: a report with no disconfirming observable is incomplete.
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
        elif keys == WEB_KEYS:
            _split_undated(out)
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
    if keys == WEB_KEYS:
        _split_undated(out)
    return out


_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_NOT_FOUND = re.compile(r"^\s*(not found|none found|n/?a|unknown|none)\b", re.I)


def _lead_date(item: Any) -> str | None:
    """The item's own date: its first `|`-field, which must be YYYY-MM-DD."""
    return _day(str(item).split("|")[0].strip().split(" ")[0])


def _split_undated(out: dict) -> dict:
    """Every claim dated, or refused into `undated_claims` -- never dropped.

    A list item under DATED_LIST_KEYS whose first field is not a date is MOVED
    to `undated_claims` as "<key>: <item>". A twelve-answer that is not "not
    found" and carries no date anywhere is KEPT on the card (it is the answer)
    and ALSO listed in `undated_claims`, so nothing reads it as dated evidence.
    """
    und: list[str] = []
    for k in DATED_LIST_KEYS:
        v = out.get(k)
        if not isinstance(v, list):
            continue
        keep = []
        for x in v:
            if _lead_date(x):
                keep.append(x)
            else:
                und.append(f"{k}: {_clean(x, 300)}")
        out[k] = keep
    for k in ANSWER_KEYS:
        v = out.get(k)
        if isinstance(v, str) and v.strip() and not _NOT_FOUND.match(v) \
                and not _DATE_RE.search(v):
            und.append(f"{k}: {_clean(v, 200)}")
    out["undated_claims"] = und
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
    # v2: the six narrative keys are fed from the twelve answers they overlap;
    # the rest stay None (not asked -> unknown, never invented).
    for k, src in (("product", "demand_product"), ("demand", "price_volume_mix"),
                   ("pricing_power", "margin_collapse_risk"),
                   ("competition", "low_cost_substitute"), ("team", None),
                   ("market_strategy", "ceo_promised")):
        c[k] = web.get(k) if web.get(k) is not None else (web.get(src) if src else None)
    for k in SYNTH_KEYS:
        c[k] = synth.get(k)
    cat_urls = [s.split("|")[3].strip() for s in (engine.get("engine_upcoming_dates") or [])
                if len(s.split("|")) > 3 and s.split("|")[3].strip()]
    c["sources"] = _merge_lists(web.get("sources"), cat_urls)
    c["openclaw_log_path"] = meta.get("openclaw_log_path")
    c["openclaw_elapsed_s"] = _num(meta.get("openclaw_elapsed_s"), 2)
    c["deepseek_cost_usd"] = _num(meta.get("deepseek_cost_usd"), 6)
    # ── beyond the spec: the twelve answers, the X reads, the dated claims,
    # the promises, the refused undated claims and provenance, flat ──
    for k in ANSWER_KEYS:
        c[f"web_{k}"] = web.get(k)
    for k in DATED_LIST_KEYS:
        c[k] = list(web.get(k) or [])
    c["undated_claims"] = list(web.get("undated_claims") or [])
    c["web_parse"] = web.get("parse")
    c["synth_status"] = synth.get("synth_status")
    c["synth_model"] = synth.get("synth_model")
    c["engine_unavailable"] = engine.get("engine_unavailable")
    c["engine_last_filed"] = engine.get("engine_last_filed")
    for k in ("openclaw_status", "openclaw_cost_usd", "quest_model", "source",
              "trigger", "run_utc"):
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
    lines += what_changed_lines(cards, root=r)
    p = r / ds / "DIGEST.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


# ──────────────────────── previous cards and the diff ───────────────────────

def _is_refused(card: dict) -> bool:
    return str(card.get("verdict", "")).startswith("REFUSED_") or bool(card.get("_unreadable"))


def card_history(ticker: str, *, root: Path | None = None) -> list[dict]:
    """Every readable, non-refused card of `ticker`, oldest first, across all
    date folders."""
    r = Path(root) if root is not None else cards_root()
    if not r.exists():
        return []
    name = f"{_safe_name(ticker)}.json"
    out = []
    for d in sorted(x for x in r.iterdir() if x.is_dir() and _day(x.name) == x.name):
        f = d / name
        if not f.exists():
            continue
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(c, dict) and not _is_refused(c):
            out.append(c)
    return out


def previous_card(ticker: str, before: Any, *, root: Path | None = None) -> dict | None:
    """The latest non-refused card of `ticker` dated strictly before `before`."""
    b = _asof_date(before).isoformat()
    prev = [c for c in card_history(ticker, root=root) if str(c.get("asof")) < b]
    return prev[-1] if prev else None


def last_card_index(*, root: Path | None = None) -> dict[str, str]:
    """ticker -> the asof of its latest non-refused card, over every folder."""
    r = Path(root) if root is not None else cards_root()
    out: dict[str, str] = {}
    if not r.exists():
        return out
    for d in sorted(x for x in r.iterdir() if x.is_dir() and _day(x.name) == x.name):
        for c in read_cards(d.name, root=r):
            if c.get("ticker") and not _is_refused(c):
                out[str(c["ticker"]).upper()] = d.name
    return out


def diff_cards(prev: dict | None, cur: dict) -> dict:
    """The twelve answers (and the verdict) of `cur` vs `prev`.

    Returns {"prev_asof", "verdict_change", "changed", "new", "gone",
    "unchanged", "schema_change"}. Answers are compared after whitespace/case
    normalisation; a v1 previous card has none of the twelve keys, which is
    reported as a schema change rather than as twelve "new" answers.
    """
    if prev is None:
        return {"prev_asof": None, "first_card": True}
    def norm(v):
        return re.sub(r"\s+", " ", str(v or "")).strip().lower()
    out = {"prev_asof": prev.get("asof"), "changed": [], "new": [], "gone": [],
           "unchanged": []}
    pv, cv = prev.get("verdict"), cur.get("verdict")
    out["verdict_change"] = None if (pv, prev.get("confidence")) == (cv, cur.get("confidence")) \
        else f"{pv}/{prev.get('confidence')} -> {cv}/{cur.get('confidence')}"
    if not any(f"web_{k}" in prev for k in ANSWER_KEYS):
        out["schema_change"] = f"{prev.get('schema') or 'thesis_card/v1'} -> {cur.get('schema')}"
        return out
    for k in ANSWER_KEYS:
        a, b = norm(prev.get(f"web_{k}")), norm(cur.get(f"web_{k}"))
        if a == b:
            out["unchanged"].append(k)
        elif not a:
            out["new"].append(k)
        elif not b:
            out["gone"].append(k)
        else:
            out["changed"].append(k)
    return out


def what_changed_lines(cards: list[dict], *, root: Path | None = None) -> list[str]:
    """The digest section: per ticker, what changed since its previous card."""
    lines = ["", "## What changed since the last card", ""]
    n = 0
    for c in cards:
        if c.get("_unreadable") or not c.get("ticker"):
            continue
        d = diff_cards(previous_card(c["ticker"], c.get("asof"), root=root), c)
        trig = f" -- trigger: {_clean(c.get('trigger'), 160)}" if c.get("trigger") else ""
        if d.get("first_card"):
            lines.append(f"- **{c['ticker']}**: first card{trig}")
            n += 1
            continue
        head = f"- **{c['ticker']}** vs {d['prev_asof']}{trig}"
        if d.get("verdict_change"):
            head += f"; verdict {d['verdict_change']}"
        if d.get("schema_change"):
            lines.append(head + f"; schema {d['schema_change']} (answers not comparable)")
            n += 1
            continue
        lines.append(head + f"; {len(d['changed'])} changed, {len(d['new'])} new, "
                     f"{len(d['gone'])} gone, {len(d['unchanged'])} unchanged")
        for k in d["changed"] + d["new"]:
            lines.append(f"  - {k}: {_clean(c.get(f'web_{k}'), 200)}")
        n += 1
    if n == 0:
        lines.append("(no cards)")
    return lines


# ─────────────────────── dated claims -> web_events rows ────────────────────
#
# Rule 6 (session order 2026-09-26): every OpenClaw result = structured
# evidence + timestamp + forecast + future grade. Each DATED claim a card
# carries becomes (1) a row in the card claims ledger with `source_id =
# "openclaw:<handle or site>"` and `first_seen_utc` = the card's run time, and
# (2) a `web_events` row where the closed vocabulary has a type for it.
#
# `web_events.validate` accepts only its own 25 types and keeps a fixed set of
# fields: it has no `claim` type and no `source_id` field. So the source rides
# in `retrieved_by` (its "who fetched this" field) and an untyped claim lives
# in the claims ledger only, with the refusal written beside it -- a claim the
# ledger cannot hold is a counted finding, not a silent drop.

CLAIM_SCHEMA = "thesis_claim/v1"

#: text pattern -> `event_vocabulary` id. First match wins; none -> "claim".
_VOCAB_RULES: tuple[tuple[str, str], ...] = (
    (r"\b(upgrad|downgrad)", "analyst_rating_change"),
    (r"\binitiat\w* (coverage|at)\b", "analyst_initiation"),
    (r"\bprice target|\bPT\b|\btarget (to|raised|cut|lowered)", "analyst_target_change"),
    (r"\bpre-?announce", "earnings_preannouncement"),
    (r"\bguid(e|ance|ed)\b|\boutlook\b", "guidance_change"),
    (r"\b(earnings|results|EPS|quarter(ly)? revenue|reported revenue)\b", "earnings_report"),
    (r"\b(acquir|merger|takeover|to buy)\w*", "mergers_acquisitions"),
    (r"\b(buyback|repurchase)", "stock_buyback"),
    (r"\bdividend (cut|suspend)", "dividend_cut_or_suspension"),
    (r"\bdividend\b", "dividend_increase"),
    (r"\b(offering|dilut|convertible notes)", "equity_issuance_dilution"),
    (r"\b(FDA|approv|PDUFA|CRL|EMA)\b", "regulatory_approval"),
    (r"\b(investigat|subpoena|probe|antitrust|DOJ|FTC)\b", "regulatory_investigation_or_action"),
    (r"\b(lawsuit|class action|sued|litigation)\b", "litigation_filed"),
    (r"\b(contract|order|award|partnership|deal with|agreement)\b", "new_contract_or_partnership"),
    (r"\b(launch|unveil|introduc|ship(s|ping|ped)|sampl)\w*", "product_launch_or_innovation"),
    (r"\b(shortage|constrain|sold out|capacity|allocation|lead time)\w*", "growth_constraint_cited"),
    (r"\b(tariff|export control|trade polic)\w*", "tariff_or_trade_policy"),
    (r"\b(CEO|CFO|chief \w+ officer)\b.*\b(appoint|named|hire|join)", "management_change_appointment"),
    (r"\b(resign|depart|step(s|ped)? down|retir)\w*", "management_change_departure"),
)

#: event_vocabulary id -> web_events type (the ledger's own closed set).
VOCAB_TO_WEB: dict[str, str] = {
    "analyst_rating_change": "analyst_revision", "analyst_target_change": "analyst_revision",
    "analyst_initiation": "analyst_revision", "earnings_report": "earnings_release",
    "earnings_preannouncement": "earnings_release", "guidance_change": "guidance_change",
    "mergers_acquisitions": "mna", "stock_buyback": "buyback",
    "dividend_increase": "dividend_change", "dividend_cut_or_suspension": "dividend_change",
    "equity_issuance_dilution": "offering", "regulatory_approval": "regulatory_decision",
    "regulatory_investigation_or_action": "regulatory_decision",
    "litigation_filed": "litigation", "new_contract_or_partnership": "contract_win",
    "product_launch_or_innovation": "product_launch",
    "growth_constraint_cited": "supplier_constraint",
    "management_change_appointment": "management_language_change",
    "management_change_departure": "management_language_change",
}

_WIRES = ("reuters.", "bloomberg.", "apnews.", "dowjones.", "wsj.", "prnewswire.",
          "businesswire.", "globenewswire.", "nikkei.", "yna.co.kr", "cnbc.", "ft.com")


def vocab_type(text: str) -> str:
    """A claim's `event_vocabulary` id by a declared keyword rule, else "claim"."""
    try:
        from backend.services import event_vocabulary as V
        known = set(V.EVENT_TYPES)
    except Exception:                                              # noqa: BLE001
        known = None
    for pat, vid in _VOCAB_RULES:
        if re.search(pat, str(text or ""), re.I) and (known is None or vid in known):
            return vid
    return "claim"


def _domain(url: str) -> str:
    m = re.match(r"^\s*https?://([^/\s]+)", str(url or ""), re.I)
    d = m.group(1).lower() if m else ""
    return d[4:] if d.startswith("www.") else d


def _source_id(src: str, url: str) -> str:
    """openclaw:<@handle> for X, else openclaw:<site>; lower-case, no spaces."""
    s = str(src or "").strip()
    if s.startswith("@"):
        return "openclaw:@" + re.sub(r"[^A-Za-z0-9_]", "", s[1:]).lower()
    site = _domain(url) or (_domain("https://" + s) if not re.search(r"\s", s) else "")
    site = site or re.sub(r"[^a-z0-9._-]+", "_", s.lower()).strip("_") or "unknown"
    return f"openclaw:{site}"


def claim_items(card: dict) -> list[dict]:
    """Every DATED claim on a card, parsed: the three X lists and `claims`.
    Items whose date does not parse were already moved to `undated_claims`."""
    out = []
    t = str(card.get("ticker") or "").upper()
    for k in X_LIST_KEYS:
        for it in card.get(k) or []:
            f = [x.strip() for x in str(it).split("|")]
            d = _lead_date(it)
            if not d or len(f) < 3:
                continue
            handle = f[1] if f[1].startswith("@") else "@" + f[1].lstrip("@")
            url = next((x for x in f[3:] if x.lower().startswith("http")), "")
            url = url or f"https://x.com/{handle[1:]}"
            out.append({"ticker": t, "list": k, "question_key": k, "claim_utc": d,
                        "source": handle, "source_url": url, "text": f[2][:200]})
    for it in card.get("claims") or []:
        f = [x.strip() for x in str(it).split("|")]
        d = _lead_date(it)
        if not d or len(f) < 5:
            if d and len(f) >= 3:         # short form: date | source | text
                out.append({"ticker": t, "list": "claims", "question_key": None,
                            "claim_utc": d, "source": f[1], "source_url": "",
                            "text": f[-1][:200]})
            continue
        out.append({"ticker": t, "list": "claims", "question_key": f[1] or None,
                    "claim_utc": d, "source": f[2], "source_url": f[3],
                    "text": " | ".join(f[4:])[:200]})
    for c in out:
        c["source_id"] = _source_id(c["source"], c["source_url"])
        c["event_type"] = vocab_type(c["text"])
    return out


def claim_id(item: dict) -> str:
    return hashlib.sha256(json.dumps(
        [item.get("ticker"), item.get("source_id"), item.get("claim_utc"),
         re.sub(r"\s+", " ", str(item.get("text", "")).strip().lower())]).encode()
    ).hexdigest()[:16]


def web_event_row(item: dict, *, run_utc: str) -> tuple[dict | None, str | None]:
    """A `web_events` row for one claim, or (None, why) when none fits."""
    wtype = VOCAB_TO_WEB.get(item.get("event_type") or "")
    if wtype is None:
        return None, (f"no web_events type fits event_type {item.get('event_type')!r} "
                      f"(web_events has no generic 'claim' type)")
    try:
        from backend.services import web_events as WE
        reg = WE.SOURCE_REGISTRY
    except Exception as exc:                                       # noqa: BLE001
        return None, f"web_events unavailable: {type(exc).__name__}"
    url = str(item.get("source_url") or "")
    dom = _domain(url)
    if not dom:
        return None, "claim carries no http(s) URL; web_events needs a checkable page"
    is_x = dom in ("x.com", "twitter.com")
    first_party = item.get("list") in ("x_company_posts", "x_ceo_posts")
    if is_x:
        st = "x"
    elif dom.endswith("sec.gov"):
        st = "sec"
    elif wtype in reg.get("company_ir", {}).get("types", ()):
        st = "company_ir"
    else:
        st = "news"
    if st not in reg or wtype not in reg[st]["types"]:
        return None, f"web_events source_type {st!r} may not carry {wtype!r}"
    if st == "sec":
        cs = "REGULATOR"
    elif first_party:
        cs = "DIRECT_COMPANY_STATEMENT"
    elif is_x:
        cs = "FORUM_CLAIM"
    elif ("investor" in dom or dom.startswith("ir.")) and st == "company_ir":
        cs = "DIRECT_COMPANY_STATEMENT"
    elif any(w in dom for w in _WIRES):
        cs = "MAJOR_WIRE"
    else:
        cs = "AGGREGATOR"
    return {"ticker": item["ticker"], "entity": item["source_id"], "source_type": st,
            "source_url": url, "event_type": wtype, "claim": item["text"],
            "evidence_date": item["claim_utc"], "observed_at": run_utc,
            "retrieved_by": item["source_id"], "confidence_source": cs}, None


def claims_path() -> Path:
    return cards_root() / "claims" / "claims.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    out = []
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
    return out


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


def _local_web_events_append(rows: list[dict], path: Path) -> dict:
    """`web_events.append`'s contract (validate, refuse-and-count, dedupe by
    event_id) written to `path` -- for a run against a non-default root."""
    from backend.services import web_events as WE
    ok, refused = [], []
    for r in rows:
        try:
            ok.append(WE.validate(r))
        except WE.WebEventRefused as exc:
            refused.append({"row": {k: r.get(k) for k in ("ticker", "event_type",
                                                          "source_url")},
                            "why": str(exc)[:300]})
    seen = {e.get("event_id") for e in _read_jsonl(path)}
    new = []
    for e in ok:
        if e["event_id"] not in seen:
            seen.add(e["event_id"])
            new.append(e)
    _append_jsonl(path, new)
    return {"receipt": "web_events.append(local)", "path": str(path),
            "accepted": len(ok), "written": len(new), "duplicates": len(ok) - len(new),
            "refused": len(refused), "refusals": refused[:10]}


def write_evidence(card: dict, *, run_utc: str | None = None,
                   events_path: Path | None = None,
                   claims_file: Path | None = None) -> dict:
    """The card's dated claims -> the claims ledger + `web_events` rows.

    IDEMPOTENT: a claim is keyed by (ticker, source_id, date, text) and written
    once to the claims ledger; `web_events` dedupes by its own event_id. A claim
    dated after the run is refused (a source cannot be read before it exists).
    `events_path=None` writes the real `web_events` ledger via `append`.
    """
    run_utc = run_utc or card.get("run_utc") or datetime.utcnow().isoformat(timespec="seconds") + "+00:00"
    cf = Path(claims_file) if claims_file is not None else claims_path()
    have = {r.get("claim_id") for r in _read_jsonl(cf)}
    items = claim_items(card)
    rows, wrows, res = [], [], {"n_claims": len(items), "n_future_refused": 0,
                                "n_already_written": 0, "n_untyped": 0}
    for it in items:
        if it["claim_utc"] > str(run_utc)[:10]:
            res["n_future_refused"] += 1
            continue
        cid = claim_id(it)
        wr, why = web_event_row(it, run_utc=run_utc)
        if it["event_type"] == "claim":
            res["n_untyped"] += 1
        if wr is not None:
            wrows.append(wr)
        if cid in have:
            res["n_already_written"] += 1
            continue
        have.add(cid)
        rows.append({"schema": CLAIM_SCHEMA, "claim_id": cid, "ticker": it["ticker"],
                     "card_hash": card.get("card_hash"), "card_asof": card.get("asof"),
                     "list": it["list"], "question_key": it["question_key"],
                     "claim_utc": it["claim_utc"], "first_seen_utc": run_utc,
                     "source_id": it["source_id"], "source": it["source"],
                     "source_url": it["source_url"], "event_type": it["event_type"],
                     "text": it["text"], "web_event_type": (wr or {}).get("event_type"),
                     "web_event_refused": why})
    _append_jsonl(cf, rows)
    res["claims_written"] = len(rows)
    res["claims_path"] = str(cf)
    if wrows:
        if events_path is None:
            from backend.services import web_events as WE
            res["web_events"] = WE.append(wrows, day=str(run_utc)[:10])
        else:
            res["web_events"] = _local_web_events_append(wrows, Path(events_path))
    else:
        res["web_events"] = {"accepted": 0, "written": 0, "refused": 0}
    res["n_untyped_claims_ledger_only"] = sum(1 for r in rows if r["web_event_refused"])
    return res


# ─────────────────────────────── the promise ledger ─────────────────────────
#
# "What the CEO promised / did they deliver": a promise is a dated, gradeable
# statement. Each becomes ONE `promise` row (idempotent by hash of ticker, text
# and promised date) with a `promise:v1` forecast row at the due horizon; the
# next card that returns the same promise with DELIVERED or MISSED appends ONE
# `grade` row. Append-only: a promise's history is the record, and its current
# status is its latest grade.

PROMISE_SCHEMA = "promise/v1"
PROMISE_STATUSES = ("OPEN", "DELIVERED", "MISSED")
PROMISE_SPECIALIST = "promise:v1"
PROMISE_MECHANISM = "promise_v1"
#: ~a quarter when no due date is stated.
PROMISE_DEFAULT_HORIZON = 60
PROMISE_P = 0.5
PROMISE_CONTRACT = (
    "promise:v1 -> ledger. One row per OPEN management promise at the first "
    "horizon on the grid (1,2,5,20,60,120,252) at or after the sessions to its "
    "due date (none stated -> 60; past -> 20; capped 252). P(beats SPY) = 0.50: "
    "a dated ANCHOR, not a skill claim. The promise's grade is its status in "
    "promises.jsonl (DELIVERED / MISSED, set by a later card); the read is "
    "realised excess return conditioned on that status.")


def promises_path() -> Path:
    from backend import config as C
    return Path(C.OPTIMUS_LEDGER_DIR) / "promises" / "promises.jsonl"


def _norm_text(s: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", re.sub(r"\s+", " ", str(s or "").lower())).strip()


def promise_id(ticker: str, promise_text: str, promised_utc: str) -> str:
    return hashlib.sha256(json.dumps(
        [str(ticker).upper(), _norm_text(promise_text), str(promised_utc)[:10]]
    ).encode()).hexdigest()[:16]


def parse_promise(item: str, ticker: str) -> dict | None:
    """"promised | due or none | STATUS | promise | evidence" -> a dict, or None."""
    f = [x.strip() for x in str(item).split("|")]
    d = _lead_date(item)
    if not d or len(f) < 4:
        return None
    due = _day(f[1].replace("due", "").strip().split(" ")[0]) if f[1] else None
    st = (re.findall(r"[A-Za-z]+", f[2]) or [""])[0].upper()
    if st not in PROMISE_STATUSES:
        return None
    text = f[3][:400]
    if not text:
        return None
    return {"ticker": str(ticker).upper(), "promise_text": text, "promised_utc": d,
            "due_utc": due, "status": st,
            "evidence": " | ".join(f[4:])[:400] if len(f) > 4 else ""}


def promise_state(rows: Iterable[dict]) -> dict[str, dict]:
    """promise_id -> the promise row with `status` = its latest grade."""
    out: dict[str, dict] = {}
    for r in rows:
        pid = r.get("promise_id")
        if r.get("row_type") == "promise":
            out[pid] = dict(r)
        elif r.get("row_type") == "grade" and pid in out:
            out[pid]["status"] = r.get("status")
            out[pid]["graded_utc"] = r.get("graded_utc")
    return out


def open_promises(ticker: str, *, path: Path | None = None) -> list[dict]:
    st = promise_state(_read_jsonl(Path(path) if path else promises_path()))
    return [p for p in st.values() if p.get("ticker") == str(ticker).upper()
            and p.get("status") == "OPEN"]


def _match_existing(p: dict, state: dict[str, dict]) -> str | None:
    """Exact id, else the same ticker + promised date with >= 60% word overlap
    (the quest is told to copy the text exactly; this catches small drift)."""
    pid = promise_id(p["ticker"], p["promise_text"], p["promised_utc"])
    if pid in state:
        return pid
    a = set(_norm_text(p["promise_text"]).split())
    best, best_j = None, 0.0
    for k, q in state.items():
        if q.get("ticker") != p["ticker"] or q.get("promised_utc") != p["promised_utc"]:
            continue
        b = set(_norm_text(q.get("promise_text")).split())
        j = len(a & b) / max(1, len(a | b))
        if j > best_j:
            best, best_j = k, j
    return best if best_j >= 0.6 else None


def promise_horizon(due_utc: str | None, today: Any) -> int:
    """The first grid horizon at or after the sessions from `today` to due."""
    from backend.services import belief_state as B
    if not due_utc:
        return PROMISE_DEFAULT_HORIZON
    import numpy as np
    n = int(np.busday_count(_asof_date(today).isoformat(), str(due_utc)[:10]))
    if n <= 0:
        return 20
    for h in B.HORIZONS:
        if h >= n:
            return h
    return max(B.HORIZONS)


def promise_forecast_records(prom: dict, *, today: Any, made_at: str | None = None) -> list:
    from backend.services import belief_state as B
    h = promise_horizon(prom.get("due_utc"), today)
    return [B.make_prediction(
        ticker=prom["ticker"], specialist=PROMISE_SPECIALIST,
        observable=B.Observable.BEATS_BENCHMARK, horizon_days=h,
        probability=PROMISE_P, benchmark=FORECAST_BENCHMARK,
        thesis=f"management promise ({prom['promised_utc']}): {prom['promise_text']}"[:1200],
        counter_thesis="the promise is MISSED, or delivered and already priced",
        next_observable=f"due {prom.get('due_utc') or 'unstated'}",
        model=str(prom.get("model") or "openclaw"), model_version=PROMISE_SCHEMA,
        prompt=PROMISE_CONTRACT, input_snapshot={k: prom.get(k) for k in (
            "promise_id", "promise_text", "promised_utc", "due_utc", "status",
            "card_hash")},
        made_at=made_at, mechanism_id=PROMISE_MECHANISM,
        decision_date=_asof_date(today).isoformat(),
        inputs_used={"source": "promise_ledger", "promise_id": prom["promise_id"],
                     "card_hash": prom.get("card_hash"), "due_utc": prom.get("due_utc")},
        licence="PRODUCT_EXPERIMENT",
        notes_text=f"promise anchor h={h}; graded by promises.jsonl status")]


def write_promises(card: dict, *, today: Any, run_utc: str | None = None,
                   path: Path | None = None, forecast_path: Path | None = None) -> dict:
    """The card's promises -> `promise` rows (new), `grade` rows (an OPEN
    promise now DELIVERED/MISSED) and `promise:v1` forecast rows.

    IDEMPOTENT: a promise row once per promise_id; a grade row once per
    (promise_id, status); a forecast row once per (promise_id, horizon).
    """
    from backend.services import belief_state as B
    pp = Path(path) if path is not None else promises_path()
    run_utc = run_utc or card.get("run_utc") or datetime.utcnow().isoformat(timespec="seconds") + "+00:00"
    rows = _read_jsonl(pp)
    state = promise_state(rows)
    graded = {(r.get("promise_id"), r.get("status")) for r in rows
              if r.get("row_type") == "grade"}
    have_fc = set()
    for r in B.read_predictions(forecast_path):
        if r.get("specialist") == PROMISE_SPECIALIST:
            have_fc.add(((r.get("inputs_used") or {}).get("promise_id"),
                         int(r.get("horizon_days") or 0)))
    new_rows, recs = [], []
    res = {"n_promises": 0, "promises_written": 0, "grades_written": 0,
           "forecast_rows_written": 0, "n_unparseable": 0, "unchanged": 0}
    t = str(card.get("ticker") or "").upper()
    for it in card.get("promises") or []:
        p = parse_promise(it, t)
        if p is None:
            res["n_unparseable"] += 1
            continue
        res["n_promises"] += 1
        pid = _match_existing(p, state)
        if pid is None:
            pid = promise_id(t, p["promise_text"], p["promised_utc"])
            row = {"schema": PROMISE_SCHEMA, "row_type": "promise", "promise_id": pid,
                   **p, "first_seen_utc": run_utc, "card_hash": card.get("card_hash"),
                   "card_asof": card.get("asof"), "model": card.get("quest_model")}
            new_rows.append(row)
            state[pid] = dict(row)
            res["promises_written"] += 1
            if p["status"] == "OPEN":
                for r in promise_forecast_records(row, today=today):
                    key = (pid, r.horizon_days)
                    if key not in have_fc:
                        have_fc.add(key)
                        recs.append(r)
            continue
        cur = state[pid].get("status")
        if p["status"] != "OPEN" and cur == "OPEN" and (pid, p["status"]) not in graded:
            new_rows.append({"schema": PROMISE_SCHEMA, "row_type": "grade",
                             "promise_id": pid, "ticker": t, "status": p["status"],
                             "evidence": p["evidence"], "graded_utc": run_utc,
                             "card_hash": card.get("card_hash"),
                             "card_asof": card.get("asof")})
            graded.add((pid, p["status"]))
            state[pid]["status"] = p["status"]
            res["grades_written"] += 1
        else:
            res["unchanged"] += 1
    _append_jsonl(pp, new_rows)
    if recs:
        B.append(recs, path=forecast_path)
    res["forecast_rows_written"] = len(recs)
    res["path"] = str(pp)
    return res


# ─────────────────────────────── card triggers ──────────────────────────────
#
# A name is re-carded when something happened, not on a calendar alone:
#   (a) it ENTERED a frozen book or the funnel shortlist after its last card
#   (b) >= 3 distinct firms revised it in the last 10 days (revision_flow)
#   (c) an earnings / 8-K / catalyst date is within 5 sessions
#   (d) |1d move| > 2 sigma_63 with no typed event that day or the day before
#   (e) its last card is older than 30 days
# Each check is pure and takes its inputs; `compute_triggers` joins them.

TRIGGER_CLUSTER_FIRMS = int(_cfg("THESIS_CARD_TRIGGER_CLUSTER_FIRMS", 3))
TRIGGER_CLUSTER_DAYS = int(_cfg("THESIS_CARD_TRIGGER_CLUSTER_DAYS", 10))
TRIGGER_CATALYST_SESSIONS = int(_cfg("THESIS_CARD_TRIGGER_CATALYST_SESSIONS", 5))
TRIGGER_SIGMA_K = float(_cfg("THESIS_CARD_TRIGGER_SIGMA_K", 2.0))
TRIGGER_SIGMA_WINDOW = int(_cfg("THESIS_CARD_TRIGGER_SIGMA_WINDOW", 63))
TRIGGER_STALE_DAYS = int(_cfg("THESIS_CARD_TRIGGER_STALE_DAYS", 30))
#: a move older than this many calendar days before asof is not "news".
TRIGGER_MOVE_MAX_AGE_DAYS = 4


def trig_entered(member_since_utc: str | None, last_card_asof: str | None,
                 where: str = "book/funnel") -> str | None:
    if not member_since_utc:
        return None
    if last_card_asof is None or str(member_since_utc)[:10] > str(last_card_asof)[:10]:
        return f"(a) entered {where} {str(member_since_utc)[:10]}" + (
            "" if last_card_asof else " (never carded)")
    return None


def trig_revision_cluster(n_firms_recent: Any, *, min_firms: int = TRIGGER_CLUSTER_FIRMS,
                          days: int = TRIGGER_CLUSTER_DAYS) -> str | None:
    n = _num(n_firms_recent)
    if n is not None and n >= min_firms:
        return f"(b) revision cluster: {int(n)} firms in {days}d"
    return None


#: event kinds that are dated but carry no news about the business: a card is
#: not re-run for a dividend record date or a webcast replay expiring.
TRIGGER_NON_CATALYST = re.compile(
    r"dividend|record date|ex-?date|replay|promotion|warrant|proxy deadline", re.I)


def trig_catalyst(asof: Any, dated_events: Iterable[str], *,
                  sessions: int = TRIGGER_CATALYST_SESSIONS) -> str | None:
    """`dated_events`: "YYYY-MM-DD | kind | what ..." strings. Kinds matching
    TRIGGER_NON_CATALYST are not catalysts."""
    import numpy as np
    a = _asof_date(asof).isoformat()
    hits = []
    for s in dated_events or []:
        d = _lead_date(s)
        if not d or d < a:
            continue
        kind = (str(s).split("|") + ["", ""])[1]
        if TRIGGER_NON_CATALYST.search(kind):
            continue
        if int(np.busday_count(a, d)) <= sessions:
            f = [x.strip() for x in str(s).split("|")]
            hits.append(f"{d} {f[1] if len(f) > 1 else ''}".strip())
    if hits:
        return f"(c) catalyst within {sessions} sessions: " + ", ".join(sorted(set(hits))[:3])
    return None


def trig_sigma_move(closes, dates, asof: Any, typed_event_dates: Iterable[str] = (), *,
                    k: float = TRIGGER_SIGMA_K, window: int = TRIGGER_SIGMA_WINDOW,
                    max_age_days: int = TRIGGER_MOVE_MAX_AGE_DAYS) -> str | None:
    """|last 1d return| > k * sd of the `window` returns before it, on a bar
    within `max_age_days` of asof, with no typed event that day or the day before."""
    import numpy as np
    c = np.asarray(list(closes), dtype=float)
    ds = [str(d)[:10] for d in dates]
    a = _asof_date(asof)
    keep = [i for i, d in enumerate(ds) if d <= a.isoformat()]
    if len(keep) < window + 2:
        return None
    c = c[keep]
    ds = [ds[i] for i in keep]
    if (a - date.fromisoformat(ds[-1])).days > max_age_days:
        return None
    r = np.diff(np.log(c))
    last, hist = r[-1], r[-window - 1:-1]
    sd = float(np.std(hist, ddof=1))
    if not math.isfinite(sd) or sd <= 0 or abs(last) <= k * sd:
        return None
    move_d = ds[-1]
    prev_d = ds[-2]
    typed = {str(x)[:10] for x in typed_event_dates or []}
    if move_d in typed or prev_d in typed:
        return None
    return (f"(d) {move_d} move {math.expm1(last):+.1%} = {abs(last) / sd:.1f} sigma_{window} "
            f"with no typed event")


def trig_stale(last_card_asof: str | None, asof: Any, *,
               days: int = TRIGGER_STALE_DAYS) -> str | None:
    if not last_card_asof:
        return None
    age = (_asof_date(asof) - _asof_date(last_card_asof)).days
    if age > days:
        return f"(e) last card {last_card_asof} is {age}d old"
    return None


def compute_triggers(candidates: Iterable[str], *, asof: Any, last_cards: dict[str, str],
                     member_since: dict[str, tuple[str, str]] | None = None,
                     n_firms_recent: dict[str, Any] | None = None,
                     dated_events: dict[str, list[str]] | None = None,
                     bars=None, typed_events: dict[str, set] | None = None) -> list[dict]:
    """[{ticker, reasons}] for every candidate with at least one reason, sorted
    by the number of reasons (desc) then ticker. Pure: every input passed in."""
    member_since = member_since or {}
    n_firms_recent = n_firms_recent or {}
    dated_events = dated_events or {}
    typed_events = typed_events or {}
    by_sym = {}
    if bars is not None and len(bars):
        import pandas as pd
        b = bars.sort_values("date")
        for sym, g in b.groupby("symbol", sort=False):
            by_sym[str(sym).upper()] = (g["close"].astype(float).to_numpy(),
                                        pd.to_datetime(g["date"]).dt.strftime("%Y-%m-%d").tolist())
    out = []
    for t in dict.fromkeys(str(x).upper() for x in candidates):
        last = last_cards.get(t)
        reasons = []
        ms = member_since.get(t)
        r = trig_entered(ms[0], last, ms[1]) if ms else None
        if r:
            reasons.append(r)
        r = trig_revision_cluster(n_firms_recent.get(t))
        if r:
            reasons.append(r)
        r = trig_catalyst(asof, dated_events.get(t) or [])
        if r:
            reasons.append(r)
        if t in by_sym:
            r = trig_sigma_move(by_sym[t][0], by_sym[t][1], asof, typed_events.get(t) or ())
            if r:
                reasons.append(r)
        r = trig_stale(last, asof)
        if r:
            reasons.append(r)
        if reasons:
            out.append({"ticker": t, "reasons": reasons, "last_card": last})
    out.sort(key=lambda x: (-len(x["reasons"]), x["ticker"]))
    return out


# ─────────────────────────── the card as a forecast ─────────────────────────
#
# Review 2026-09-25 row 8 (accepted): the 81 verdicts were never forecast rows,
# so none of them could ever be graded. A card is evidence, not an order -- and
# a verdict nobody grades is an opinion. Each card now writes one
# `beats_benchmark` row per horizon under `specialist = thesis_card:v1`.

FORECAST_SPECIALIST = "thesis_card:v1"
FORECAST_MECHANISM = "thesis_card_v1"
FORECAST_BENCHMARK = "SPY"
#: verdict -> the probability the name beats SPY, before the confidence shrink.
VERDICT_P: dict[str, float] = {"supports": 0.60, "neutral": 0.50, "against": 0.40}
#: confidence -> the share of the distance from 0.50 that is kept.
CONFIDENCE_KEEP: dict[str, float] = {"high": 1.0, "med": 0.6, "low": 0.3}
#: ~one month and ~six months. The spec said 21 / 126 sessions; the ledger's
#: grid (`belief_state.HORIZONS` = 1, 2, 5, 20, 60, 120, 252) REFUSES any other
#: horizon ("a horizon chosen per-prediction is a free parameter"), so the rows
#: sit on its nearest points, 20 and 120. Graded on the same grid as every
#: other specialist, which is what makes them comparable at all.
FORECAST_HORIZONS: tuple[int, ...] = (20, 120)
FORECAST_CONTRACT = (
    "thesis_card:v1 -> ledger. P(ticker beats SPY over h sessions) = 0.50 + "
    "keep[confidence] * (base[verdict] - 0.50); base supports 0.60 / neutral "
    "0.50 / against 0.40; keep high 1.0 / med 0.6 / low 0.3; h in (20, 120); "
    "counter_thesis = the card's falsifier; REFUSED_* cards write nothing.")


def forecast_probability(verdict: Any, confidence: Any) -> float | None:
    """The mapping, alone. None = this card cannot be a forecast."""
    if verdict not in VERDICT_P or confidence not in CONFIDENCE_KEEP:
        return None
    return round(0.5 + CONFIDENCE_KEEP[confidence] * (VERDICT_P[verdict] - 0.5), 6)


def forecast_snapshot(card: dict) -> dict:
    """What the row saw: the card's hash, its verdict, and the engine side."""
    snap = {"card_hash": card.get("card_hash") or card_hash(card),
            "asof": card.get("asof"), "verdict": card.get("verdict"),
            "confidence": card.get("confidence")}
    for k in (*ENGINE_KEYS, "engine_unavailable", "engine_last_filed"):
        snap[k] = card.get(k)
    return snap


def forecast_records(card: dict, *, today: Any, made_at: str | None = None) -> list:
    """`belief_state.PredictionRecord`s for one card; [] for a card that is not
    a forecast (REFUSED_*, an unknown verdict or confidence, unreadable, or a
    card dated after `today` -- a forecast cannot be about evidence from the
    future)."""
    from backend.services import belief_state as B
    if not isinstance(card, dict) or card.get("_unreadable") or not card.get("ticker"):
        return []
    p = forecast_probability(card.get("verdict"), card.get("confidence"))
    if p is None:
        return []
    today_d = _asof_date(today)
    asof = _day(card.get("asof"))
    if asof is None or asof > today_d.isoformat():
        return []
    snap = forecast_snapshot(card)
    ud = card.get("upcoming_dates") or []
    nxt = str(ud[0]) if isinstance(ud, list) and ud else ""
    out = []
    for h in FORECAST_HORIZONS:
        out.append(B.make_prediction(
            ticker=str(card["ticker"]).upper(), specialist=FORECAST_SPECIALIST,
            observable=B.Observable.BEATS_BENCHMARK, horizon_days=h,
            probability=p, benchmark=FORECAST_BENCHMARK,
            thesis=str(card.get("bull") or "")[:1200],
            counter_thesis=str(card.get("falsifier") or "")[:800],
            next_observable=nxt[:300],
            model=str(card.get("synth_model") or card.get("quest_model") or "unknown"),
            model_version=str(card.get("schema") or SCHEMA_VERSION),
            prompt=FORECAST_CONTRACT, input_snapshot=snap, made_at=made_at,
            mechanism_id=FORECAST_MECHANISM, decision_date=today_d.isoformat(),
            inputs_used={"source": "thesis_card", "as_of": asof,
                         "card_hash": snap["card_hash"],
                         "card_kind": card.get("kind")},
            confidence=CONFIDENCE_KEEP[card["confidence"]],
            licence="PRODUCT_EXPERIMENT",
            notes_text=(f"thesis card {asof}: verdict {card.get('verdict')} / "
                        f"confidence {card.get('confidence')} -> p {p:.3f}")))
    return out


def forecast_rows(card: dict, *, today: Any, made_at: str | None = None) -> list[dict]:
    """The rows one card writes, as ledger dicts. See `forecast_records`."""
    from dataclasses import asdict
    return [asdict(r) for r in forecast_records(card, today=today, made_at=made_at)]


def _written_keys(ledger_rows: Iterable[dict]) -> set[tuple[str, int]]:
    """(card_hash, horizon) already in the ledger for this specialist."""
    out = set()
    for r in ledger_rows:
        if r.get("specialist") != FORECAST_SPECIALIST:
            continue
        h = (r.get("inputs_used") or {}).get("card_hash")
        if h:
            out.add((str(h), int(r.get("horizon_days") or 0)))
    return out


def write_forecasts(cards: Iterable[dict], *, today: Any,
                    path: Path | None = None) -> dict:
    """Append every card's rows that are not already in the ledger.

    IDEMPOTENT per (card_hash, horizon): a card is ONE forecast, ever. A re-run,
    a later day's backfill, or the run's per-card write followed by a backfill
    writes nothing twice (the hash covers `asof`, so tomorrow's card of the same
    name is a new card and a new forecast). The ledger is
    the record of what was written -- the card file is not touched, so its hash
    stays valid.
    """
    from backend.services import belief_state as B
    today_d = _asof_date(today).isoformat()
    have = _written_keys(B.read_predictions(path))
    recs, res = [], {"n_cards": 0, "n_not_a_forecast": 0, "n_already_written": 0,
                     "not_a_forecast": []}
    for c in cards:
        res["n_cards"] += 1
        rs = forecast_records(c, today=today_d)
        if not rs:
            res["n_not_a_forecast"] += 1
            res["not_a_forecast"].append(f"{c.get('ticker')}:{c.get('verdict')}")
            continue
        for r in rs:
            key = (r.inputs_used["card_hash"], r.horizon_days)
            if key in have:
                res["n_already_written"] += 1
                continue
            have.add(key)
            recs.append(r)
    if recs:
        B.append(recs, path=path)
    res["n_rows_written"] = len(recs)
    return res
