"""S1_social_features — the five variables of spec §2, each beside its own NULL.

    python -m scripts.night_factory_jobs S1_social_features --smoke
    python -m scripts.night_factory_jobs S1_social_features

Writes ONE panel-joinable table,
`<DATA_DIR>/optimus/social/features_<RUN_DATE>.parquet`, one row per
`(date, ticker)`, and a receipt naming every variable it could NOT compute and
the paths it looked for.

NOTHING HERE IS A SIGNAL CLAIM
==============================
Every variable in `docs/research_notes/2026-09-19/spec_social_video_pipeline.md`
§2 owes its own `docs/TRIALS/` entry before it is evaluated against a return
(§3.6, CANON §6), and not one has been written. This job computes columns and
their controls; it ranks nothing, selects nothing and joins no return. The
social rows it reads are `pit_grade: index_state` and `label_source: false`, so
the panel they join into may never take a LABEL from their timestamps —
invariant 20, and the reason `night_e1_news_return_panel` reads only
`news_registry.label_sources()`.

THE FIVE VARIABLES, AND WHY EACH ONE'S NULL IS COMPUTED BESIDE IT
=================================================================
A variable without its control is a number nobody can read. Each null answers
the specific "it would look like this anyway" for its own variable:

1. **mention_velocity** — count over its own 60-day baseline, PER SOURCE.
   Pooling Reddit and YouTube before the ratio hides which platform moved,
   which is the only thing the ratio is for.
   NULL: **shuffled ticker** — every mention's ticker is reassigned within the
   SAME DAY'S mention pool, so aggregate volume survives and ticker-specific
   information does not. A velocity indistinguishable from this carries
   market-wide chatter and nothing about the name.
2. **stance_dispersion** — Shannon entropy AND variance of the local model's
   {-1,0,+1} stance over a post's comments. BOTH, because entropy over three
   bins saturates (40/30/30 reads like 34/33/33) while variance keeps the
   spread of conviction. The pre-registration names ONE as primary before data
   accrues; this job may not pick after seeing which looks better.
   NULL: **matched-day count** — the same ticker's comments on a randomly drawn
   other day, with the mention count matched, because more comments
   mechanically raises apparent entropy and a sample-size artefact must be
   ruled out before dispersion is read as information.
3. **hype_lateness** — the cross-sectional percentile of mention velocity,
   beside the TRAILING 20-session return as of the day before. Murat's
   hypothesis is that these correlate at the top, i.e. velocity is lagging once
   extreme.
   NULL: the shuffled-ticker percentile, plus the literature's own version (the
   WSB peak-attention −8.5% HPR finding) which the pre-registration must
   distinguish from rather than reproduce.
4. **growth_constraint_cited** — a count per issuer from TYPED rows carrying
   the v3 id (`event_vocabulary._V3_ADDED`, chunk 19). No text is read here;
   this reads what L2 already wrote.
5. **supplier_link** — the `supplier` entity on those same typed rows, kept
   only when the typed row came from an 8-K Exhibit 99 source. This is the
   event-conditioned, daily-resolution successor `NEGATIVE_RESULTS.md` §12
   named as the ONLY admissible revival of the supply-chain corpse — and it is
   registered fresh, not treated as a re-run of it.

THE MODEL SEAM, AND THE ENUM ON THE WIRE
========================================
Stance typing goes through the same local reader as `L2_typed_events`
(`free_inference.complete`, backend `local_gguf`), and it NEVER starts or stops
a server: with nothing listening it writes `PENDING_MODEL` with the candidate
comment list FROZEN AND HASHED, so the run that happens when a server is up
asks the same question rather than a similar one.

The stance enum is in the LITERAL system text the model receives, not only in
the validator. That is the 2026-09-13 lesson at this repo's own expense
(`feedback_a_prompt_that_refers_to_a_schema_it_never_sends.md`): DeepSeek
refused 54% of a 1,200-row paid run because `SYSTEM_PROMPT` said "matching the
schema you have been given" while the enum lived only in the validator.
`stance_wire_system()` reconstructs exactly what is sent and a test asserts the
enum is in it.

RUN_DATE IS NEVER A LITERAL. An idle-queue job runs every day; three of them
dated their outputs `2026-09-12` by literal on 2026-09-18 and overwrote
committed receipts three nights running.

LICENCE: PRODUCT_EXPERIMENT. No order path, no promotion, no claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import numpy as np

from backend.services import event_vocabulary as vocab
from backend.services import llm_language as _lang

JOB = "S1_social_features"
LICENCE = "PRODUCT_EXPERIMENT"
STAGE = "signal"

#: Never a literal. Unset means TODAY; `NIGHT_RUN_DATE` reproduces a past night.
RUN_DATE = os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")

ET = ZoneInfo("America/New_York")

#: The baseline window for mention velocity, in DAYS. Spec §2.1's own number.
BASELINE_DAYS = 60

#: Days of social rows read. Baseline plus the day itself plus slack for the
#: matched-day null, which needs OTHER days of the same ticker to draw from.
LOOKBACK_DAYS = BASELINE_DAYS + 30

#: Sessions of trailing return for hype-lateness. Spec §2.3's own number.
TRAILING_SESSIONS = 20

#: Comments typed for stance in ONE pass. The local reader manages roughly 20
#: rows a minute per worker and the lab's box is 30 minutes, so this is a
#: number a box can finish rather than one that guarantees a kill.
MAX_STANCE_ROWS = 400

#: The seed for both draws (shuffled ticker, matched day). DECLARED, and
#: printed on the receipt: `hash()` is salted per process, so a seed derived
#: from it draws a different control every night under one printed number.
SEED = 20260919

#: Minimum comments under a post before a dispersion number is computed at all.
#: Entropy over two observations is not a measurement of debate.
MIN_COMMENTS_FOR_DISPERSION = 5

#: Every refusal this job can return, by name. A variable that refuses is still
#: NAMED in the receipt with the paths it looked for — `B_exclusion_screen`'s
#: rule: a family that declared five variables and reported three is a
#: different family, and the reader has to see which happened.
REFUSALS = ("NO_SOCIAL_ROWS", "PENDING_MODEL", "NO_BARS", "NO_TYPED_ROWS")

#: The five, in spec order. The receipt carries one block per name whether or
#: not it computed.
VARIABLES = ("mention_velocity", "stance_dispersion", "hype_lateness",
             "growth_constraint_cited", "supplier_link")

#: The typed-event id §2.4/§2.5 are keyed to. Read from the vocabulary, not
#: retyped: a literal here that drifted from the table would be a job counting
#: an id nobody added.
CONSTRAINT_ID = "growth_constraint_cited"

#: Which corpus sources count as an EXHIBIT for §2.5's supplier link. The
#: Ex-99 body source landed in chunk 20 T1; the feed row carries no body and
#: can never produce a supplier mention, so counting it would inflate the
#: denominator with rows that could not have answered.
EXHIBIT_SOURCES = ("sec_edgar_8k_ex99_body",)


class SocialFeaturesRefused(RuntimeError):
    """This job will not report a column it cannot support. Named, never silent."""


# --------------------------------------------------------------------- paths

def _data_root() -> Path:
    from backend import config as _config
    return Path(_config.DATA_DIR) / "optimus"


def social_dir() -> Path:
    return _data_root() / "social"


def typed_dir() -> Path:
    return _data_root() / "typed_events"


def bars_path() -> Path:
    return _data_root() / "prices_2025_26" / "bars.parquet"


def features_path(run_date: str | None = None) -> Path:
    return social_dir() / f"features_{run_date or RUN_DATE}.parquet"


def out_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / f"night_factory_{RUN_DATE}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ the rows

def load_social_rows(*, days: int = LOOKBACK_DAYS, run_date: str | None = None,
                     rows: list[dict] | None = None) -> tuple[list[dict], dict]:
    """Every social row inside the window, plus what was read.

    `rows` is injectable so the tests drive the whole job without a corpus.
    """
    if rows is not None:
        read = {"files": 0, "rows": len(rows), "injected": True}
        return list(rows), read
    d = social_dir()
    if not d.is_dir():
        return [], {"files": 0, "rows": 0, "dir": str(d)}
    end = datetime.fromisoformat(run_date or RUN_DATE).date()
    start = end - timedelta(days=int(days))
    out: list[dict] = []
    files = sorted(d.glob("*_[0-9][0-9][0-9][0-9]-[0-9][0-9].jsonl"))
    for p in files:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            day = row_date(row)
            if day and start.isoformat() <= day <= end.isoformat():
                out.append(row)
    return out, {"files": len(files), "rows": len(out), "dir": str(d),
                 "window": [start.isoformat(), end.isoformat()]}


def row_date(row: dict) -> str:
    """The row's EASTERN date, from the `first_seen_utc` WE wrote.

    Eastern because that is the calendar the return side is on
    (`night_e1_news_return_panel`'s own rule), and `first_seen_utc` because the
    provider's own stamp is index-state and a feature stamped on one would read
    the future in a way no test would catch.
    """
    stamp = str(row.get("first_seen_utc") or "")
    if not stamp:
        return ""
    try:
        dt = datetime.fromisoformat(stamp)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ET).date().isoformat()


def mention_table(rows: list[dict]) -> list[tuple[str, str, str, str]]:
    """`[(date, source, ticker, row_id)]` — one entry per (row, ticker) pair.

    A row naming three tickers is three mentions, which is what a mention COUNT
    means; collapsing it to one would make a broad market post look like a
    single-name post.
    """
    out = []
    for r in rows:
        day = row_date(r)
        if not day:
            continue
        src = str(r.get("source") or "")
        rid = str(r.get("id") or "")
        for t in (r.get("ticker_mentions") or []):
            out.append((day, src, str(t).upper(), rid))
    return out


# ------------------------------------------------------- 1. mention velocity

def mention_velocity(mentions: list[tuple[str, str, str, str]], *, day: str,
                     baseline_days: int = BASELINE_DAYS) -> dict:
    """`{(source, ticker): {n, baseline, velocity}}` for ONE day.

    `velocity = n(t, d) / mean(n(t, d-baseline..d-1))`, computed SEPARATELY per
    source (spec §2.1: pooling before the ratio hides which platform moved).

    A ticker with a zero baseline gets `velocity = None`, not `inf` and not a
    silent 1.0: "first ever mention" and "ten times its usual" are different
    facts and a number that merged them would be read as the second.
    """
    end = datetime.fromisoformat(day).date()
    window = {(end - timedelta(days=i)).isoformat() for i in range(1, baseline_days + 1)}
    today: Counter = Counter()
    prior: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for d, src, tick, _rid in mentions:
        if d == day:
            today[(src, tick)] += 1
        elif d in window:
            prior[(src, tick)][d] += 1
    out: dict[tuple[str, str], dict] = {}
    keys = set(today) | set(prior)
    for key in keys:
        n = int(today.get(key, 0))
        days_seen = prior.get(key, Counter())
        baseline = (sum(days_seen.values()) / float(baseline_days)) if days_seen else 0.0
        out[key] = {
            "n": n,
            "baseline_per_day": round(baseline, 4),
            "baseline_days_observed": len(days_seen),
            "velocity": (round(n / baseline, 4) if baseline > 0 else None),
        }
    return out


def shuffled_ticker_null(mentions: list[tuple[str, str, str, str]], *, day: str,
                         seed: int = SEED,
                         baseline_days: int = BASELINE_DAYS) -> dict:
    """THE NULL: RELABEL the day's tickers, so each count meets the wrong history.

    THE OBVIOUS IMPLEMENTATION IS A NO-OP, and it was written first and caught
    by its own test. Permuting the ticker LABELS of a day's mentions permutes a
    multiset: twenty NVDA mentions and ten AMD mentions, shuffled, are still
    twenty NVDA and ten AMD. Every per-ticker count is identical, so the
    "control" velocity equals the real velocity exactly — a null that cannot
    differ from what it is controlling, which is the shape of a guard that
    always passes.

    What the null has to break is the PAIRING between today's count and that
    NAME'S OWN 60-day baseline (and, downstream, that name's own forward
    return). So the day's DISTINCT TICKERS are permuted instead: the day's
    count vector survives exactly — same aggregate volume, same distribution of
    counts, same per-source split — and each count is attached to a different
    name's history. A velocity indistinguishable from this one is a reading of
    how much chatter there was, not of which name it was about.
    """
    rng = np.random.default_rng(int(seed))
    by_day: dict[str, list[int]] = defaultdict(list)
    for i, (d, _src, _t, _rid) in enumerate(mentions):
        by_day[d].append(i)
    shuffled = list(mentions)
    for d in sorted(by_day):
        idxs = by_day[d]
        names = sorted({mentions[i][2] for i in idxs})
        perm = rng.permutation(len(names))
        mapping = {names[k]: names[int(perm[k])] for k in range(len(names))}
        for i in idxs:
            dd, src, t, rid = mentions[i]
            shuffled[i] = (dd, src, mapping[t], rid)
    return mention_velocity(shuffled, day=day, baseline_days=baseline_days)


# ---------------------------------------------------- 2. stance dispersion

#: The schema, draft-07. The enum lives here AND in the literal system text.
STANCE_SCHEMA: dict = {
    "$id": "aegis://schemas/social_stance_row.json",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "stance": {"type": "integer", "enum": [-1, 0, 1]},
        "stance_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence_span": {"type": "string", "maxLength": 200},
    },
    "required": ["stance", "stance_confidence"],
}

STANCE_SYSTEM = """You read ONE comment from a retail-investing forum about one named company
and report the commenter's STANCE on that company's stock.

stance is an integer and exactly one of:
  -1  bearish  — the comment expects the stock to fall, or argues against owning it
   0  neutral  — no directional view, a question, a joke, or off-topic
   1  bullish  — the comment expects the stock to rise, or argues for owning it

Report the COMMENTER'S view, never your own and never the company's prospects.
Sarcasm counts as the view it conveys. A comment that names no view is 0; that
is a successful reading, not a failure.

stance_confidence is a number between 0 and 1 for how clear the stance is.
evidence_span is a short quotation, copied verbatim from the comment.

Output ONE JSON object and nothing else. No prose, no code fence."""


def stance_system_with_schema() -> str:
    """The system prompt WITH the schema the rules refer to.

    The enum is spelled out in the TEXT, not only in the validator. 2026-09-13:
    `event_extraction.SYSTEM_PROMPT` said "matching the schema you have been
    given" while the 43-id enum lived only in `SCHEMA`, and DeepSeek answered
    54% of the first flush with ids it had never been shown.
    """
    allowed = ", ".join(str(v) for v in STANCE_SCHEMA["properties"]["stance"]["enum"])
    head = ("The schema (JSON Schema draft-07). `stance` MUST be one of exactly "
            f"these three integers and nothing else: {allowed}")
    return (STANCE_SYSTEM + "\n\n" + head + "\n\nFull schema:\n"
            + json.dumps(STANCE_SCHEMA, sort_keys=True, separators=(",", ":")))


def stance_wire_system() -> str:
    """EXACTLY what the model sees, language pin included."""
    return _lang.pin(stance_system_with_schema())


STANCE_USER = """Company: {ticker}
Comment:
{text}

Report {ticker} stance per your instructions. Output the JSON object only."""


def stance_prompt_hash() -> str:
    """sha256 over (wire system, user template, canonical schema).

    All three: a schema edit changes what the model was asked as surely as a
    prompt edit does, and a row carrying only a prompt hash could not tell them
    apart.
    """
    payload = json.dumps({"system": stance_wire_system(),
                          "user_template": STANCE_USER,
                          "schema": STANCE_SCHEMA},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_stance(raw: str) -> dict:
    """`{stance, stance_confidence, evidence_span}` or `{refused: CLASS}`.

    Fences are stripped and nothing else is repaired. A reply that does not
    validate is a REFUSAL with its class, never a coerced zero: a bad reply
    silently read as "neutral" would move the dispersion number it was supposed
    to be excluded from.
    """
    text = _FENCE.sub("", (raw or "").strip()).strip()
    if not text:
        return {"refused": "REFUSED_UNPARSEABLE", "detail": "empty reply"}
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"refused": "REFUSED_UNPARSEABLE", "detail": f"json.loads: {exc}"}
    if not isinstance(obj, dict):
        return {"refused": "REFUSED_SCHEMA", "detail": "the reply is not an object"}
    if obj.get("stance") not in STANCE_SCHEMA["properties"]["stance"]["enum"]:
        return {"refused": "REFUSED_SCHEMA",
                "detail": f"stance {obj.get('stance')!r} is not in "
                          f"{STANCE_SCHEMA['properties']['stance']['enum']}"}
    try:
        conf = float(obj.get("stance_confidence"))
    except (TypeError, ValueError):
        return {"refused": "REFUSED_SCHEMA", "detail": "stance_confidence is not a number"}
    if not 0.0 <= conf <= 1.0:
        return {"refused": "REFUSED_SCHEMA", "detail": f"stance_confidence {conf} outside [0,1]"}
    return {"stance": int(obj["stance"]), "stance_confidence": conf,
            "evidence_span": str(obj.get("evidence_span") or "")[:200]}


def dispersion(stances: list[int]) -> dict:
    """BOTH entropy and variance, never one.

    Entropy over three bins saturates fast — 40/30/30 reads as "high debate"
    exactly like 34/33/33 — while variance keeps the spread of conviction. The
    spec requires both on the receipt and ONE named primary in the
    pre-registration BEFORE data accrues; picking after seeing which looks
    better is the thing CANON §6 forbids.
    """
    n = len(stances)
    if n == 0:
        return {"n": 0, "entropy": None, "variance": None, "mean": None,
                "counts": {"-1": 0, "0": 0, "1": 0}}
    counts = Counter(int(s) for s in stances)
    ent = 0.0
    for bin_ in (-1, 0, 1):
        p = counts.get(bin_, 0) / n
        if p > 0:
            ent -= p * math.log(p)
    arr = np.asarray(stances, dtype=float)
    return {
        "n": n,
        "entropy": round(float(ent), 6),
        "entropy_max": round(float(math.log(3)), 6),
        "variance": round(float(arr.var(ddof=0)), 6),
        "mean": round(float(arr.mean()), 6),
        "counts": {str(b): int(counts.get(b, 0)) for b in (-1, 0, 1)},
    }


def stance_candidates(rows: list[dict], *, day: str,
                      max_rows: int = MAX_STANCE_ROWS) -> list[dict]:
    """The comments a dispersion number for `day` would be computed over.

    Comments only — a post is the thing being debated, not a vote in the
    debate. Ordered by id so the frozen list is reproducible and a resumed run
    asks the same question.
    """
    out = []
    for r in rows:
        if r.get("kind") != "comment":
            continue
        if row_date(r) != day:
            continue
        for t in (r.get("ticker_mentions") or []):
            out.append({"id": str(r.get("id") or ""), "ticker": str(t).upper(),
                        "parent_id": str(r.get("parent_id") or ""),
                        "text": str(r.get("text") or "")[:1500]})
    out.sort(key=lambda u: (u["ticker"], u["id"]))
    return out[: int(max_rows)]


def fingerprint(units: list[dict]) -> dict:
    """The frozen candidate list, hashed. A PENDING_MODEL receipt is only
    reproducible if the run that follows it reads the same rows."""
    keys = sorted(f"{u['ticker']}:{u['id']}" for u in units)
    payload = json.dumps(keys, separators=(",", ":"))
    return {"n_units": len(units),
            "sha256": hashlib.sha256(payload.encode()).hexdigest()[:16],
            "first": keys[:3], "last": keys[-3:]}


def probe_reader(backend: str = "local_gguf") -> str | None:
    """Is the reader answering? NEVER starts it, never stops it."""
    from scripts.night_l2_typed_events import _probe
    return _probe(backend)


def type_stances(units: list[dict], *, backend: str = "local_gguf",
                 complete: Callable | None = None) -> dict:
    """One call per comment through the local reader. Refusals are counted."""
    if complete is None:
        from backend.services.free_inference import complete as complete_
        complete = complete_
    typed: list[dict] = []
    refusals: Counter = Counter()
    for u in units:
        prompt = STANCE_USER.format(ticker=u["ticker"], text=u["text"])
        try:
            reply = complete(backend, prompt, system=stance_system_with_schema(),
                             max_tokens=160, temperature=0.0,
                             purpose="s1_social_stance")
        except Exception as exc:                                   # noqa: BLE001
            refusals["REFUSED_READER_ERROR"] += 1
            typed.append({**u, "refused": "REFUSED_READER_ERROR",
                          "detail": f"{type(exc).__name__}: {exc}"})
            continue
        got = parse_stance(str(getattr(reply, "text", "") or ""))
        if got.get("refused"):
            refusals[got["refused"]] += 1
        typed.append({**u, **got, "model": getattr(reply, "model", None)})
    return {"rows": typed, "refusals": dict(refusals),
            "typed": sum(1 for t in typed if "stance" in t)}


def dispersion_by_ticker(typed_rows: list[dict]) -> dict:
    """`{ticker: dispersion(...)}` over the comments that produced a stance."""
    by: dict[str, list[int]] = defaultdict(list)
    for t in typed_rows:
        if "stance" in t:
            by[t["ticker"]].append(int(t["stance"]))
    return {k: dispersion(v) for k, v in by.items()}


def matched_day_null(rows: list[dict], *, day: str, counts: dict[str, int],
                     seed: int = SEED) -> dict:
    """THE NULL: the same ticker's comments on a RANDOM OTHER day, count-matched.

    More comments mechanically raises apparent entropy, so a dispersion number
    has to beat the same statistic computed on a same-size sample of the same
    ticker from a day nothing happened. This returns the DRAW — which day and
    which comment ids — and not a dispersion: the stance model has to read
    those comments too, and a null whose inputs were chosen after seeing the
    result is not a null.
    """
    rng = np.random.default_rng(int(seed) + 1)
    by_ticker_day: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        if r.get("kind") != "comment":
            continue
        d = row_date(r)
        if not d or d == day:
            continue
        for t in (r.get("ticker_mentions") or []):
            by_ticker_day[(str(t).upper(), d)].append(str(r.get("id") or ""))
    out: dict[str, dict] = {}
    for ticker, want in sorted(counts.items()):
        days = sorted({d for (t, d) in by_ticker_day if t == ticker})
        if not days:
            out[ticker] = {"matched": False,
                           "why": "this ticker has no comment on any other day in the window"}
            continue
        pick = days[int(rng.integers(0, len(days)))]
        pool = sorted(by_ticker_day[(ticker, pick)])
        out[ticker] = {
            "matched": len(pool) >= want,
            "day": pick,
            "wanted": int(want),
            "available": len(pool),
            "comment_ids": pool[: int(want)],
            "why": (None if len(pool) >= want
                    else "the drawn day has fewer comments than the target day; "
                         "the count is NOT matched and the comparison is not paired"),
        }
    return out


# -------------------------------------------------------- 3. hype lateness

def trailing_returns(day: str, tickers: list[str], *,
                     bars=None, sessions: int = TRAILING_SESSIONS) -> tuple[dict, dict]:
    """`{ticker: trailing return}` over the `sessions` closing PRICES BEFORE `day`.

    STRICTLY BEFORE: a trailing window that includes the day it is computed for
    has already seen the day it is describing (defect #5 of 2026-09-10, the
    liquidity screen that read its own entry session).
    """
    import pandas as pd

    if bars is None:
        p = bars_path()
        if not p.is_file():
            return {}, {"refused": "NO_BARS", "path": str(p),
                        "why": ("hype-lateness is a comparison against the "
                                "trailing return; without prices the variable "
                                "is refused BY NAME rather than reported as a "
                                "percentile of nothing")}
        bars = pd.read_parquet(p)
    b = bars.copy()
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    cutoff = pd.Timestamp(day)
    out: dict[str, float] = {}
    for sym in tickers:
        g = b[(b["symbol"] == sym) & (b["date"] < cutoff)].sort_values("date")
        if len(g) < sessions + 1:
            continue
        window = g.tail(sessions + 1)
        first, last = float(window["close"].iloc[0]), float(window["close"].iloc[-1])
        if first > 0:
            out[sym] = round(last / first - 1.0, 6)
    return out, {"refused": "", "sessions": sessions, "names_priced": len(out),
                 "rule": "strictly BEFORE the feature date; the day itself is never in the window"}


def percentile_rank(values: dict[str, float]) -> dict[str, float]:
    """Cross-sectional percentile within the day, 0..1. Ties share their rank."""
    items = [(k, v) for k, v in values.items() if v is not None]
    if not items:
        return {}
    arr = np.asarray([v for _k, v in items], dtype=float)
    out = {}
    for k, v in items:
        out[k] = round(float((arr <= v).mean()), 6)
    return out


# ------------------------------------ 4/5. typed rows: constraints, suppliers

def load_typed_rows(*, path: Path | None = None,
                    rows: list[dict] | None = None) -> tuple[list[dict], dict]:
    """Typed-event rows carrying the v3 id. Reads what L2 wrote; types nothing."""
    if rows is not None:
        return list(rows), {"files": 0, "rows": len(rows), "injected": True}
    d = path or typed_dir()
    if not d.is_dir():
        return [], {"files": 0, "rows": 0, "dir": str(d), "refused": "NO_TYPED_ROWS"}
    out: list[dict] = []
    files = sorted(d.glob("*.jsonl"))
    for p in files:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event_type") == CONSTRAINT_ID:
                out.append(row)
    return out, {"files": len(files), "rows": len(out), "dir": str(d),
                 "refused": "" if files else "NO_TYPED_ROWS"}


def constraint_counts(typed: list[dict], *, day: str | None = None) -> dict:
    """`{ticker: n}` — how many `growth_constraint_cited` rows name each issuer."""
    out: Counter = Counter()
    for row in typed:
        if day and _typed_date(row) != day:
            continue
        for t in (row.get("tickers") or []):
            out[str(t).upper()] += 1
    return dict(out)


def _typed_date(row: dict) -> str:
    stamp = str(row.get("document_date") or row.get("first_seen_utc") or "")
    return stamp[:10]


def supplier_links(typed: list[dict], *, day: str | None = None,
                   exhibit_sources: tuple[str, ...] = EXHIBIT_SOURCES) -> dict:
    """`{issuer: [{supplier, named_input, source}]}` from the typed row's entities.

    Only rows whose SOURCE is an 8-K Exhibit 99 body count. The Ex-99 FEED row
    carries no body at all and could never have produced a supplier mention, so
    counting it would put rows in the denominator that had no chance to answer.
    """
    out: dict[str, list[dict]] = defaultdict(list)
    for row in typed:
        if str(row.get("source") or "") not in exhibit_sources:
            continue
        if day and _typed_date(row) != day:
            continue
        ent = row.get("entities") or {}
        supplier = str(ent.get("supplier") or "").strip()
        if not supplier:
            continue
        for t in (row.get("tickers") or []):
            out[str(t).upper()].append({
                "supplier": supplier,
                "named_input": str(ent.get("named_input") or "").strip(),
                "source": row.get("source"),
                "url": row.get("url"),
            })
    return dict(out)


# -------------------------------------------------------------------- the job

def S1_social_features(*, smoke: bool = False, run: int = 1,   # noqa: N802
                       run_date: str | None = None,
                       backend: str = "local_gguf",
                       complete: Callable | None = None,
                       social_rows: list[dict] | None = None,
                       typed_rows: list[dict] | None = None,
                       bars=None, seed: int = SEED) -> dict:
    """One parquet, one receipt, five variables, each beside its own null."""
    import pandas as pd

    t0 = datetime.now(timezone.utc)
    day = run_date or RUN_DATE
    base: dict[str, Any] = {
        "job": JOB, "licence": LICENCE, "stage": STAGE, "run": int(run),
        "run_date": day, "smoke": bool(smoke), "llm_spend_usd": 0.0,
        "spend_note": "the LOCAL reader costs compute, not dollars",
        "seed": int(seed),
        "seed_note": ("DECLARED. hash() is salted per process, so a seed "
                      "derived from it draws a different control every night "
                      "under one printed number"),
        "variables_declared": list(VARIABLES),
        "refusal_names_declared": list(REFUSALS),
        "vocabulary": {"version": vocab.VOCABULARY_VERSION,
                       "hash": vocab.VOCABULARY_HASH,
                       "constraint_id": CONSTRAINT_ID},
        "stance_contract": {
            "backend": backend,
            "prompt_hash": stance_prompt_hash(),
            "enum_on_the_wire": str(
                STANCE_SCHEMA["properties"]["stance"]["enum"]) in stance_wire_system(),
            "why": ("the enum is in the LITERAL system text and not only in "
                    "the validator -- 2026-09-13, when a prompt referred to a "
                    "schema it never sent and 54% of the first flush came back "
                    "with invented values"),
        },
        "pit_rule": (
            "every social row is pit_grade index_state and label_source false. "
            "This table may be JOINED to the return panel and may never supply "
            "its LABEL (invariant 20). The feature date is the EASTERN date of "
            "the `first_seen_utc` we wrote, and the trailing return window ends "
            "STRICTLY BEFORE it."),
        "not_a_claim": (
            "no variable here has a TRIALS entry yet (spec §3.6). This job "
            "computes columns and their controls; it ranks nothing, selects "
            "nothing and joins no return."),
        "output": str(features_path(day)),
    }

    rows, read = load_social_rows(run_date=day, rows=social_rows)
    base["social_read"] = read
    variables: dict[str, dict] = {}

    if not rows:
        for name in VARIABLES:
            variables[name] = {"computed": False, "refused": "NO_SOCIAL_ROWS",
                               "paths": [str(social_dir())]}
        return {
            **base, "variables": variables, "rows": 0,
            "headline": (f"NO_SOCIAL_ROWS: nothing under {social_dir()} inside the "
                         f"{LOOKBACK_DAYS}-day window. Both keys are absent "
                         f"(REDDIT_KEYS_ABSENT / YOUTUBE_KEY_ABSENT), so this is "
                         f"the expected state until Murat creates them."),
            "verdict": ("REFUSED BY NAME -- the collector has no key yet, so "
                        "there is no row to compute a variable from. Every "
                        "variable is NAMED as refused rather than silently "
                        "absent."),
            "elapsed_s": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
            "written_utc": _now(),
        }

    mentions = mention_table(rows)
    vel = mention_velocity(mentions, day=day)
    vel_null = shuffled_ticker_null(mentions, day=day, seed=seed)
    sources = sorted({s for _d, s, _t, _r in mentions})
    tickers = sorted({t for (_s, t) in vel})
    variables["mention_velocity"] = {
        "computed": True,
        "sources": sources,
        "pairs": len(vel),
        "tickers": len(tickers),
        "baseline_days": BASELINE_DAYS,
        "per_source": ("computed SEPARATELY per source: pooling before the "
                       "ratio hides which platform moved"),
        "zero_baseline": ("velocity is None, never inf and never 1.0 -- 'first "
                          "ever mention' and 'ten times its usual' are "
                          "different facts"),
        "null": {"name": "shuffled_ticker",
                 "how": ("each mention's ticker reassigned within its OWN "
                         "day's pool: aggregate volume survives, "
                         "ticker-specific information does not"),
                 "pairs": len(vel_null)},
    }

    # --- 2. stance dispersion (the only model-touching variable) ---------
    units = stance_candidates(rows, day=day, max_rows=8 if smoke else MAX_STANCE_ROWS)
    fp = fingerprint(units)
    disp: dict[str, dict] = {}
    stance_block: dict[str, Any] = {"computed": False, "candidates": fp,
                                    "min_comments": MIN_COMMENTS_FOR_DISPERSION}
    if not units:
        stance_block["refused"] = ""
        stance_block["why"] = "no comment on this date names a ticker"
    else:
        why = None if complete is not None else probe_reader(backend)
        if why:
            stance_block["refused"] = "PENDING_MODEL"
            stance_block["why"] = why
            stance_block["never_starts_a_server"] = (
                "the candidate list is frozen and hashed, so the run that "
                "happens when a server IS up asks the same question")
        else:
            got = type_stances(units, backend=backend, complete=complete)
            disp = dispersion_by_ticker(got["rows"])
            counts = {k: v["n"] for k, v in disp.items()}
            stance_block.update({
                "computed": True,
                "typed": got["typed"],
                "refusals": got["refusals"],
                "tickers_with_a_number": sum(
                    1 for v in disp.values()
                    if v["n"] >= MIN_COMMENTS_FOR_DISPERSION),
                "both_statistics": ("entropy AND variance, never one: entropy "
                                    "over three bins saturates, variance keeps "
                                    "the spread of conviction. The prereg names "
                                    "ONE as primary before data accrues"),
                "null": {"name": "matched_day_count",
                         "draw": matched_day_null(rows, day=day, counts=counts,
                                                  seed=seed),
                         "how": ("the same ticker's comments on a randomly "
                                 "drawn OTHER day with the count matched -- "
                                 "more comments mechanically raises apparent "
                                 "entropy and that artefact must be ruled out "
                                 "before dispersion is read as information"),
                         "status": ("the DRAW only. Those comments must be "
                                    "read by the same model before the null "
                                    "has a number, and a null whose inputs "
                                    "were chosen after seeing the result is "
                                    "not a null")},
            })
    variables["stance_dispersion"] = stance_block

    # --- 3. hype lateness -------------------------------------------------
    trail, trail_meta = trailing_returns(day, tickers, bars=bars)
    vel_by_ticker = {t: max((v["velocity"] or 0.0) for (s, tt), v in vel.items()
                            if tt == t) for t in tickers}
    pct_vel = percentile_rank(vel_by_ticker)
    pct_trail = percentile_rank(trail)
    vel_null_by_ticker = {t: max((v["velocity"] or 0.0)
                                 for (s, tt), v in vel_null.items() if tt == t)
                          for t in tickers if any(tt == t for (_s, tt) in vel_null)}
    pct_vel_null = percentile_rank(vel_null_by_ticker)
    variables["hype_lateness"] = {
        "computed": not trail_meta.get("refused"),
        "refused": trail_meta.get("refused", ""),
        "trailing": trail_meta,
        "names_with_both": len(set(pct_vel) & set(pct_trail)),
        "hypothesis": ("mention velocity and TRAILING return correlate at high "
                       "percentiles -- velocity is lagging once already "
                       "extreme, so {high velocity, high trailing return, LOW "
                       "dispersion} should be the WORST forward cell, not the "
                       "best"),
        "null": {"name": "shuffled_ticker_percentile",
                 "names": len(pct_vel_null),
                 "literature": ("the WSB peak-attention finding (-8.5% HPR at "
                                "peak attention) is the LITERATURE's version of "
                                "this null; the prereg must distinguish from it "
                                "rather than reproduce it")},
    }

    # --- 4/5. typed rows --------------------------------------------------
    typed, typed_meta = load_typed_rows(rows=typed_rows)
    base["typed_read"] = typed_meta
    cc = constraint_counts(typed)
    sl = supplier_links(typed)
    variables["growth_constraint_cited"] = {
        "computed": not typed_meta.get("refused"),
        "refused": typed_meta.get("refused", ""),
        "paths": [str(typed_dir())],
        "issuers": len(cc),
        "rows": len(typed),
        "id": CONSTRAINT_ID,
        "reads_no_text": "this counts what L2 already typed; it calls no model",
    }
    variables["supplier_link"] = {
        "computed": not typed_meta.get("refused"),
        "refused": typed_meta.get("refused", ""),
        "exhibit_sources": list(EXHIBIT_SOURCES),
        "issuers": len(sl),
        "links": sum(len(v) for v in sl.values()),
        "why_exhibit_only": ("the Ex-99 FEED row carries no body and could "
                             "never produce a supplier mention; counting it "
                             "would put rows in the denominator that had no "
                             "chance to answer"),
        "negative_results_12": (
            "this is the event-conditioned, daily-resolution successor §12 "
            "named as the ONLY admissible revival of the supply-chain corpse, "
            "and it is registered fresh rather than treated as a re-run"),
        "null": {"name": "same_sector_non_supplier",
                 "status": ("NOT COMPUTED here: it needs a sector map and a "
                            "matched control pool, and it is the prereg's "
                            "first requirement rather than a column")},
    }

    # --- the table --------------------------------------------------------
    records = []
    for t in tickers:
        rec: dict[str, Any] = {"date": day, "ticker": t}
        for s in sources:
            cell = vel.get((s, t))
            null_cell = vel_null.get((s, t))
            rec[f"mention_n_{s}"] = (cell or {}).get("n", 0)
            rec[f"mention_velocity_{s}"] = (cell or {}).get("velocity")
            rec[f"mention_velocity_null_{s}"] = (null_cell or {}).get("velocity")
        d = disp.get(t) or {}
        rec["stance_n"] = d.get("n", 0)
        rec["stance_entropy"] = d.get("entropy")
        rec["stance_variance"] = d.get("variance")
        rec["stance_mean"] = d.get("mean")
        rec["hype_velocity_pct"] = pct_vel.get(t)
        rec["hype_velocity_pct_null"] = pct_vel_null.get(t)
        rec["trailing_20d_return"] = trail.get(t)
        rec["trailing_20d_return_pct"] = pct_trail.get(t)
        rec["growth_constraint_cited_n"] = int(cc.get(t, 0))
        rec["supplier_link_n"] = len(sl.get(t, []))
        rec["supplier_named_inputs"] = "; ".join(
            x["named_input"] for x in sl.get(t, []) if x.get("named_input"))
        records.append(rec)

    frame = pd.DataFrame.from_records(records)
    path = features_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)

    computed = [k for k, v in variables.items() if v.get("computed")]
    refused = {k: v.get("refused") for k, v in variables.items() if v.get("refused")}
    return {
        **base,
        "variables": variables,
        "rows": len(records),
        "columns": list(frame.columns),
        "tickers": len(tickers),
        "computed": computed,
        "refused": refused,
        "headline": (f"{len(records)} (date, ticker) row(s) for {day}; "
                     f"{len(computed)} of {len(VARIABLES)} variable(s) computed, "
                     f"{len(refused)} refused ({', '.join(sorted(set(refused.values()))) or 'none'})"),
        "next_test": (
            "a column is not a finding. Each of the five owes its own TRIALS "
            "entry with its primary statistic named BEFORE any return is "
            "joined -- and §2.5 will score RESURRECTION against "
            "NEGATIVE_RESULTS §12, which is allowed only if the draft names "
            "daily event-conditioning as the changed instrument."),
        "verdict": ("SMOKE -- proves the job runs end to end; no count may be "
                    "read from it" if smoke else
                    f"{len(computed)} variable(s) computed with their nulls; "
                    f"{len(refused)} refused BY NAME. Nothing here is a signal."),
        "elapsed_s": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
        "written_utc": _now(),
    }


__all__ = ["BASELINE_DAYS", "CONSTRAINT_ID", "EXHIBIT_SOURCES", "JOB",
           "MAX_STANCE_ROWS", "MIN_COMMENTS_FOR_DISPERSION", "REFUSALS",
           "RUN_DATE", "SEED", "STANCE_SCHEMA", "STANCE_SYSTEM",
           "S1_social_features", "SocialFeaturesRefused", "TRAILING_SESSIONS",
           "VARIABLES", "constraint_counts", "dispersion",
           "dispersion_by_ticker", "features_path", "fingerprint",
           "load_social_rows", "load_typed_rows", "matched_day_null",
           "mention_table", "mention_velocity", "parse_stance",
           "percentile_rank", "probe_reader", "row_date",
           "shuffled_ticker_null", "social_dir", "stance_candidates",
           "stance_prompt_hash", "stance_system_with_schema",
           "stance_wire_system", "supplier_links", "trailing_returns",
           "type_stances", "typed_dir"]
