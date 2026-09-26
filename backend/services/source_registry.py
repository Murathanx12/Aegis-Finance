"""The source/actor graph -- every source is a forecaster that has not earned a weight yet.

WHY (chunk B, session order 2026-09-26, rule 3)
===============================================
    "Social is an attention layer, not a truth layer: a source's claims become
     forecast rows and earn a reliability weight; X and Reddit never generate
     orders; a source may be kept as a reversal indicator."

The IBES actor corpus (`docs/FINDING_2026-08-23_ANALYST_RELIABILITY.md`) showed
that an analyst's track record persists out of sample. This module gives every
OTHER source -- a newswire, an 8-K feed, a brokerage, a CEO's X account, a
subreddit -- the same treatment: a registry entry with a declared `kind`, every
dated claim frozen as a `beats_benchmark` forecast row under
`specialist = "source:<source_id>"`, and a scoreboard that starts every source at
`n=0, weight=prior` and lets it earn its way.

THREE THINGS THIS MODULE NEVER DOES
===================================
* It never places, sizes or proposes an order. It does not import the broker,
  and `test_source_registry.py` fails if any code path here or in
  `scripts/source_reads.py` names `pc_broker`.
* It never trusts a handle it has not read. A handle a discovery quest proposed
  is `verified: false` until a DATED post from that handle has been read.
* It never scores a claim by the date it was READ as if it were the date it was
  MADE. `claim_utc` (what the source says) and `made_at` (when we saw it) are
  separate; the forecast row is made when we saw it, so it cannot be backfilled.

Horizons: the ledger grid (`belief_state.HORIZONS`) refuses 21, so the "21d"
cell sits on 20 -- the same choice `thesis_card` made, for the same reason.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
import yaml

from backend import config as _config

logger = logging.getLogger(__name__)


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


# ── constants ────────────────────────────────────────────────────────────────
KINDS: tuple[str, ...] = (
    "company", "ceo_founder", "engineer_researcher", "sell_side", "fund_manager",
    "journalist", "industry_specialist", "government_regulatory",
    "retail_influencer", "reddit_community", "newswire", "filing",
)
#: kinds whose reads go through OpenClaw on a social platform (never an order).
SOCIAL_PLATFORMS: tuple[str, ...] = ("x", "reddit")
#: kinds whose items count as the "mainstream first-seen" of a fact.
MAINSTREAM_KINDS: frozenset[str] = frozenset({"newswire", "filing"})

SOURCES_DIR: Path = Path(_cfg("SOURCES_DIR", _config.OPTIMUS_LEDGER_DIR / "sources"))
REGISTRY_PATH: Path = SOURCES_DIR / "registry.yaml"
CLAIMS_PATH: Path = SOURCES_DIR / "claims.jsonl"
NEWS_CORPUS_DIR: Path = _config.OPTIMUS_LEDGER_DIR / "news_corpus"
TARGET_REVISIONS: Path = _config.OPTIMUS_LEDGER_DIR / "analyst" / "target_revisions.parquet"
BARS_PATH: Path = _config.OPTIMUS_LEDGER_DIR / "prices_2025_26" / "bars.parquet"

SPECIALIST_PREFIX = "source:"
FORECAST_BENCHMARK = "SPY"
FORECAST_MECHANISM = "source_claim_v1"
#: stated direction -> P(name beats SPY). A source's claim is worth +/-0.10
#: until its own track record says otherwise; the weight is EARNED, not assumed.
DIRECTION_P: dict[str, float] = {"up": 0.60, "down": 0.40}
#: the grid the scoreboard reads (1d / 5d / "21d" = 20 on the ledger grid).
SCORE_HORIZONS: tuple[int, ...] = (1, 5, 20)
#: a claim and a mainstream item on the same ticker within this many hours are
#: treated as the same fact for the lead-time metric.
LEAD_WINDOW_H: float = float(_cfg("SOURCE_LEAD_WINDOW_H", 48.0))
#: a source earns a skill-based weight only after this many graded rows at a horizon.
MIN_N_FOR_WEIGHT: int = int(_cfg("SOURCE_MIN_N_FOR_WEIGHT", 20))
#: crowding signature (signed 21d minus signed 5d) below this = a fading pop.
REVERSAL_THRESHOLD: float = float(_cfg("SOURCE_REVERSAL_THRESHOLD", -0.01))
MIN_N_FOR_REVERSAL: int = int(_cfg("SOURCE_MIN_N_FOR_REVERSAL", 10))
#: the reputation key with the source id in place of the arm.
KEY_SOURCE_OBSERVABLE_HORIZON: tuple[str, ...] = ("source_id", "observable", "horizon_days")

CLAIM_CONTRACT = (
    "source_claim_v1 -> ledger. A dated claim by a registered source about a "
    "ticker becomes P(ticker beats SPY over h sessions) = 0.60 if the stated "
    "direction is up, 0.40 if down; no stated direction = no forecast row (the "
    "claim is still counted). Raw, unshrunk; the source's weight is earned by "
    "forecast_reputation keyed on source_id. Never an order.")


class RegistryRefused(ValueError):
    """The registry (or a source in it) is not well-formed. Never loaded half."""


# ── the source ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Source:
    source_id: str
    kind: str
    handle: str = ""
    url: str = ""
    tickers_covered: tuple[str, ...] = ()
    added_utc: str = ""
    added_by: str = ""
    platform: str = ""            # x / reddit / rss / api / sec / ibes ...
    theme: str = ""
    verified: bool = True
    verified_by: str = ""         # the dated post that verified it
    found_by_quest: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tickers_covered"] = list(self.tickers_covered)
        return d

    @property
    def is_social(self) -> bool:
        return self.platform in SOCIAL_PLATFORMS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def source_from_dict(d: dict) -> Source:
    """Build one `Source`, REFUSING one with no kind or an unknown kind."""
    if not isinstance(d, dict):
        raise RegistryRefused(f"REFUSED: a registry entry must be a mapping, got {type(d).__name__}")
    sid = str(d.get("source_id") or "").strip()
    if not sid:
        raise RegistryRefused("REFUSED: a source with no source_id cannot be scored")
    kind = str(d.get("kind") or "").strip()
    if not kind:
        raise RegistryRefused(
            f"REFUSED: source {sid!r} has no kind. A source whose kind is unknown "
            f"cannot be compared with its peers, and a scoreboard of unlabelled "
            f"sources teaches nothing.")
    if kind not in KINDS:
        raise RegistryRefused(f"REFUSED: source {sid!r} kind {kind!r} is not one of {KINDS}")
    tick = d.get("tickers_covered") or ()
    if isinstance(tick, str):
        tick = [tick]
    return Source(
        source_id=sid, kind=kind, handle=str(d.get("handle") or ""),
        url=str(d.get("url") or ""),
        tickers_covered=tuple(str(t).upper() for t in tick),
        added_utc=str(d.get("added_utc") or ""), added_by=str(d.get("added_by") or ""),
        platform=str(d.get("platform") or ""), theme=str(d.get("theme") or ""),
        verified=bool(d.get("verified", True)), verified_by=str(d.get("verified_by") or ""),
        found_by_quest=str(d.get("found_by_quest") or ""), notes=str(d.get("notes") or ""))


def load_registry(path: Path | str | None = None) -> dict[str, Source]:
    """source_id -> Source. REFUSES the whole file on one bad entry or a duplicate id."""
    p = Path(path) if path else REGISTRY_PATH
    if not p.exists():
        raise RegistryRefused(f"REFUSED: no registry at {p}")
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rows = doc.get("sources") if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        raise RegistryRefused(f"REFUSED: {p} has no `sources:` list")
    out: dict[str, Source] = {}
    for d in rows:
        s = source_from_dict(d)
        if s.source_id in out:
            raise RegistryRefused(f"REFUSED: duplicate source_id {s.source_id!r}")
        out[s.source_id] = s
    return out


def save_registry(sources: dict[str, Source] | Iterable[Source],
                  path: Path | str | None = None) -> Path:
    p = Path(path) if path else REGISTRY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    items = list(sources.values()) if isinstance(sources, dict) else list(sources)
    counts: dict[str, int] = {}
    for s in items:
        counts[s.kind] = counts.get(s.kind, 0) + 1
    doc = {"schema": "source_registry/v1",
           "read_me_first": ("Every source is a forecaster that has not earned a "
                             "weight yet. Social sources are an ATTENTION layer, "
                             "never a truth layer and never an order. A handle a "
                             "quest proposed is verified: false until a dated post "
                             "from it has been read."),
           "counts_by_kind": dict(sorted(counts.items())),
           "sources": [s.to_dict() for s in sorted(items, key=lambda s: (s.kind, s.source_id))]}
    tmp = p.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120),
                   encoding="utf-8")
    tmp.replace(p)
    return p


# ── seeding ──────────────────────────────────────────────────────────────────
_CORPUS_KIND = (
    (re.compile(r"^sec_edgar"), "filing", "sec"),
    (re.compile(r"^reddit_"), "reddit_community", "reddit_rss"),
    (re.compile(r"^quantocracy"), "industry_specialist", "rss"),
)


def corpus_kind(name: str) -> tuple[str, str]:
    for rx, kind, plat in _CORPUS_KIND:
        if rx.search(name):
            return kind, plat
    return "newswire", "rss_api"


def corpus_source_id(name: str) -> str:
    return f"news:{name}"


def seed_base_sources(*, corpus_dir: Path | None = None,
                      revisions_path: Path | None = None,
                      added_by: str = "chunk_b_seed",
                      now: str | None = None) -> list[Source]:
    """The non-social seed: every news-corpus source on disk, SEC EDGAR 8-K and
    Form 4 as `filing`, and every brokerage in `target_revisions.parquet`."""
    now = now or _now()
    out: list[Source] = []
    cdir = Path(corpus_dir) if corpus_dir else NEWS_CORPUS_DIR
    if cdir.exists():
        for d in sorted(cdir.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            kind, plat = corpus_kind(d.name)
            out.append(Source(source_id=corpus_source_id(d.name), kind=kind,
                              handle=d.name, url=f"news_corpus/{d.name}",
                              added_utc=now, added_by=added_by, platform=plat,
                              notes="news corpus source (first_seen_utc per row)"))
    out.append(Source(source_id="filing:sec_edgar_8k", kind="filing", handle="8-K",
                      url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K",
                      added_utc=now, added_by=added_by, platform="sec",
                      notes="SEC EDGAR current 8-K filings (primary)"))
    out.append(Source(source_id="filing:sec_form4", kind="filing", handle="4",
                      url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4",
                      added_utc=now, added_by=added_by, platform="sec",
                      notes="SEC EDGAR Form 4 insider transactions (primary)"))
    rp = Path(revisions_path) if revisions_path else TARGET_REVISIONS
    if rp.exists():
        firms = pd.read_parquet(rp, columns=["firm"])["firm"].dropna().astype(str)
        vc = firms.value_counts()
        seen: set[str] = set()
        for firm, n in vc.items():
            sid = f"sell_side:{_slug(firm)}"
            if not _slug(firm) or sid in seen:
                continue
            seen.add(sid)
            out.append(Source(source_id=sid, kind="sell_side", handle=firm,
                              url="analyst/target_revisions.parquet", added_utc=now,
                              added_by=added_by, platform="yfinance_revisions",
                              notes=f"{int(n)} dated revisions in target_revisions.parquet"))
    return out


def x_source(handle: str, *, kind: str, tickers: Sequence[str] = (), theme: str = "",
             quest_id: str, added_by: str = "openclaw_discovery",
             name: str = "", now: str | None = None) -> Source:
    """An X handle proposed by a discovery quest -- ALWAYS `verified: false`."""
    h = "@" + str(handle).strip().lstrip("@")
    if not re.fullmatch(r"@[A-Za-z0-9_]{1,15}", h):
        raise RegistryRefused(f"REFUSED: {handle!r} is not an X handle")
    if kind not in KINDS:
        raise RegistryRefused(f"REFUSED: kind {kind!r} for {h} is not one of {KINDS}")
    return Source(source_id=f"x:{h[1:].lower()}", kind=kind, handle=h,
                  url=f"https://x.com/{h[1:]}",
                  tickers_covered=tuple(str(t).upper() for t in tickers),
                  added_utc=now or _now(), added_by=added_by, platform="x",
                  theme=theme, verified=False, found_by_quest=quest_id,
                  notes=(name or "")[:160])


def merge_sources(reg: dict[str, Source], new: Iterable[Source]) -> tuple[dict[str, Source], int]:
    """Add sources not already present. An existing entry is never overwritten
    (its verification state and provenance are the record)."""
    out = dict(reg)
    added = 0
    for s in new:
        if s.source_id in out:
            old = out[s.source_id]
            if s.tickers_covered and set(s.tickers_covered) - set(old.tickers_covered):
                out[s.source_id] = replace(old, tickers_covered=tuple(sorted(
                    set(old.tickers_covered) | set(s.tickers_covered))))
            continue
        out[s.source_id] = s
        added += 1
    return out, added


# ── verification: a handle is real once a DATED post from it has been read ──
_STATUS_URL = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status/(\d+)", re.I)


def parse_utc(v: Any) -> datetime | None:
    if v is None or v == "":
        return None
    try:
        t = pd.Timestamp(v)
    except (ValueError, TypeError):
        return None
    if pd.isna(t):
        return None
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("UTC").to_pydatetime()


def is_dated_post(source: Source, post: dict) -> bool:
    """True only for a post with a parseable timestamp AND, on X, a status URL
    under this very handle. A post dated in the future is not a post."""
    t = parse_utc(post.get("posted_utc") or post.get("claim_utc"))
    if t is None or t > datetime.now(timezone.utc) + timedelta(minutes=10):
        return False
    if source.platform == "x":
        m = _STATUS_URL.match(str(post.get("post_url") or ""))
        return bool(m) and m.group(1).lower() == source.handle.lstrip("@").lower()
    if source.platform == "reddit":
        return "reddit.com" in str(post.get("post_url") or "").lower()
    return True


def verify_with_posts(source: Source, posts: Iterable[dict]) -> Source:
    """Flip `verified` only on a dated post from this handle; otherwise unchanged."""
    if source.verified:
        return source
    for p in posts:
        if is_dated_post(source, p):
            return replace(source, verified=True,
                           verified_by=f"{p.get('post_url')} @ {parse_utc(p.get('posted_utc') or p.get('claim_utc')).isoformat()}")
    return source


# ── claims -> forecast rows (never an order) ────────────────────────────────
def claim_hash(source_id: str, ticker: str, claim_text: str, claim_utc: Any) -> str:
    t = parse_utc(claim_utc)
    payload = [str(source_id), str(ticker).upper(),
               re.sub(r"\s+", " ", str(claim_text).strip().lower()),
               t.isoformat() if t else str(claim_utc)]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:16]


def _norm_direction(direction: Any) -> str | None:
    d = str(direction or "").strip().lower()
    if d in ("up", "long", "bull", "bullish", "positive", "+1", "1", "buy"):
        return "up"
    if d in ("down", "short", "bear", "bearish", "negative", "-1", "sell"):
        return "down"
    return None


def claim_records(source_id: str, ticker: str, claim_text: str, claim_utc: Any, *,
                  direction: Any, horizon_days: int | Sequence[int] = SCORE_HORIZONS,
                  source_kind: str = "", made_at: str | None = None,
                  model: str = "openclaw:source_read", post_url: str = "") -> list:
    """`belief_state.PredictionRecord`s for ONE claim, one per horizon.

    [] when the claim has no stated direction (it is counted in the claims
    ledger, not forecast), when it is undated, or dated after `made_at`.
    """
    from backend.services import belief_state as B
    d = _norm_direction(direction)
    t = parse_utc(claim_utc)
    if d is None or t is None or not str(claim_text).strip():
        return []
    made = made_at or _now()
    made_t = parse_utc(made)
    if made_t is not None and t > made_t + timedelta(minutes=10):
        return []                     # a claim cannot be dated after we read it
    tick = str(ticker).upper()
    h_ = claim_hash(source_id, tick, claim_text, t)
    p = DIRECTION_P[d]
    hs = (horizon_days,) if isinstance(horizon_days, int) else tuple(horizon_days)
    snap = {"claim_hash": h_, "claim_utc": t.isoformat(), "source_kind": source_kind}
    out = []
    for h in hs:
        out.append(B.make_prediction(
            ticker=tick, specialist=f"{SPECIALIST_PREFIX}{source_id}",
            observable=B.Observable.BEATS_BENCHMARK, horizon_days=int(h),
            probability=p, benchmark=FORECAST_BENCHMARK,
            thesis=str(claim_text)[:1200],
            counter_thesis=f"the source's stated direction ({d}) is wrong or already priced",
            next_observable=post_url[:300], model=model, model_version=FORECAST_MECHANISM,
            prompt=CLAIM_CONTRACT, input_snapshot=snap, made_at=made,
            mechanism_id=FORECAST_MECHANISM, decision_date=made[:10],
            inputs_used={"source": "source_registry", "source_id": source_id,
                         "claim_hash": h_, "claim_utc": t.isoformat(),
                         "source_kind": source_kind, "post_url": post_url},
            licence="PRODUCT_EXPERIMENT", raw_probability=p,
            shrink_basis="none: fixed 0.5+/-0.10 by stated direction; the source's "
                         "weight is earned by forecast_reputation keyed on source_id",
            notes_text=f"source claim {source_id} {d} -> p {p:.2f}; attention, not an order"))
    return out


def claim_rows(source_id: str, ticker: str, claim_text: str, claim_utc: Any, *,
               direction: Any, horizon_days: int | Sequence[int] = SCORE_HORIZONS,
               **kw: Any) -> list[dict]:
    """The rows one claim writes, as ledger dicts. See `claim_records`."""
    return [asdict(r) for r in claim_records(source_id, ticker, claim_text, claim_utc,
                                             direction=direction,
                                             horizon_days=horizon_days, **kw)]


def _written_claim_keys(ledger_rows: Iterable[dict]) -> set[tuple[str, int]]:
    out = set()
    for r in ledger_rows:
        if not str(r.get("specialist") or "").startswith(SPECIALIST_PREFIX):
            continue
        h = (r.get("inputs_used") or {}).get("claim_hash")
        if h:
            out.add((str(h), int(r.get("horizon_days") or 0)))
    return out


def write_claims(claims: Iterable[dict], *, path: Path | None = None,
                 claims_path: Path | None = None, made_at: str | None = None) -> dict:
    """Record every claim in the claims ledger and write its forecast rows.

    IDEMPOTENT by claim hash: a claim is ONE forecast per horizon, ever -- a
    re-read of the same post writes nothing. Each `claim` is a dict with
    source_id, ticker, claim_text, claim_utc, direction, and optionally
    horizon_days, source_kind, post_url.
    """
    from backend.services import belief_state as B
    cp = Path(claims_path) if claims_path else CLAIMS_PATH
    cp.parent.mkdir(parents=True, exist_ok=True)
    have_claims = {c.get("claim_hash") for c in read_claims(cp)}
    have_rows = _written_claim_keys(B.read_predictions(path))
    made = made_at or _now()
    recs, res = [], {"n_claims": 0, "n_new_claims": 0, "n_duplicate_claims": 0,
                     "n_no_direction": 0, "n_rows_written": 0, "n_rows_already": 0}
    new_claim_lines = []
    for c in claims:
        res["n_claims"] += 1
        t = parse_utc(c.get("claim_utc"))
        if t is None:
            continue
        h_ = claim_hash(c["source_id"], c["ticker"], c["claim_text"], t)
        if h_ in have_claims:
            res["n_duplicate_claims"] += 1
        else:
            have_claims.add(h_)
            res["n_new_claims"] += 1
            new_claim_lines.append({
                "claim_hash": h_, "source_id": c["source_id"],
                "source_kind": c.get("source_kind", ""),
                "ticker": str(c["ticker"]).upper(), "claim_text": str(c["claim_text"])[:1200],
                "claim_utc": t.isoformat(), "observed_utc": made,
                "direction": _norm_direction(c.get("direction")),
                "post_url": c.get("post_url", "")})
        rs = claim_records(c["source_id"], c["ticker"], c["claim_text"], t,
                           direction=c.get("direction"),
                           horizon_days=c.get("horizon_days", SCORE_HORIZONS),
                           source_kind=c.get("source_kind", ""), made_at=made,
                           post_url=c.get("post_url", ""))
        if not rs:
            res["n_no_direction"] += 1
            continue
        for r in rs:
            key = (r.inputs_used["claim_hash"], r.horizon_days)
            if key in have_rows:
                res["n_rows_already"] += 1
                continue
            have_rows.add(key)
            recs.append(r)
    if new_claim_lines:
        with cp.open("a", encoding="utf-8") as fh:
            for line in new_claim_lines:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    if recs:
        B.append(recs, path=path)
    res["n_rows_written"] = len(recs)
    return res


def read_claims(path: Path | None = None) -> list[dict]:
    p = Path(path) if path else CLAIMS_PATH
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                logger.warning("source_registry: unparseable claims line skipped")
    return out


# ── the empirical track record ──────────────────────────────────────────────
def forward_relative_returns(claims: pd.DataFrame, bars: pd.DataFrame | None, *,
                             horizons: Sequence[int] = (1, 5, 21),
                             benchmark: str = FORECAST_BENCHMARK) -> pd.DataFrame:
    """Per claim: name return minus benchmark return over h sessions, entering at
    the close of the FIRST session strictly after the claim's UTC date (a claim
    made during a session is not assumed tradable at that session's close)."""
    cols = [f"rel_{h}d" for h in horizons]
    out = pd.DataFrame(index=claims.index, columns=cols, dtype=float)
    if bars is None or bars.empty or claims.empty:
        return out
    px = bars.pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
    px.index = pd.to_datetime(px.index)
    px = px.sort_index()
    if benchmark not in px.columns:
        return out
    dates = px.index
    for i, row in claims.iterrows():
        tick = str(row["ticker"]).upper()
        if tick not in px.columns:
            continue
        t = parse_utc(row["claim_utc"])
        if t is None:
            continue
        pos = dates.searchsorted(pd.Timestamp(t.date()) + pd.Timedelta(days=1))
        if pos >= len(dates):
            continue
        s, b = px[tick], px[benchmark]
        e_s, e_b = s.iloc[pos], b.iloc[pos]
        if not (np.isfinite(e_s) and np.isfinite(e_b)) or e_s <= 0 or e_b <= 0:
            continue
        for h in horizons:
            if pos + h >= len(dates):
                continue
            x_s, x_b = s.iloc[pos + h], b.iloc[pos + h]
            if np.isfinite(x_s) and np.isfinite(x_b):
                out.at[i, f"rel_{h}d"] = (x_s / e_s - 1.0) - (x_b / e_b - 1.0)
    return out


def crowding_signature(signed_5d: Sequence[float], signed_21d: Sequence[float]) -> dict:
    """Mean signed 21d relative return MINUS mean signed 5d. A source whose names
    pop then fade scores negative -- kept, and labelled `use_as: reversal`."""
    a5 = np.asarray([x for x in signed_5d if x is not None and np.isfinite(x)], float)
    a21 = np.asarray([x for x in signed_21d if x is not None and np.isfinite(x)], float)
    if len(a5) == 0 or len(a21) == 0:
        return {"n_5d": int(len(a5)), "n_21d": int(len(a21)), "mean_5d": None,
                "mean_21d": None, "signature": None, "use_as": "prior"}
    m5, m21 = float(a5.mean()), float(a21.mean())
    sig = m21 - m5
    n = min(len(a5), len(a21))
    if n >= MIN_N_FOR_REVERSAL and m5 > 0 and sig <= REVERSAL_THRESHOLD:
        use = "reversal"
    elif n >= MIN_N_FOR_REVERSAL:
        use = "attention"
    else:
        use = "prior"
    return {"n_5d": int(len(a5)), "n_21d": int(len(a21)), "mean_5d": m5,
            "mean_21d": m21, "signature": sig, "use_as": use}


def load_mainstream_items(tickers: Iterable[str], *, corpus_dir: Path | None = None,
                          registry: dict[str, Source] | None = None) -> pd.DataFrame:
    """Corpus rows from MAINSTREAM sources (newswire, filing) on these tickers:
    ticker, source_id, t (earliest of published_utc / first_seen_utc)."""
    want = {str(t).upper() for t in tickers}
    cdir = Path(corpus_dir) if corpus_dir else NEWS_CORPUS_DIR
    rows = []
    if not want or not cdir.exists():
        return pd.DataFrame(columns=["ticker", "source_id", "t"])
    for d in sorted(cdir.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        sid = corpus_source_id(d.name)
        kind = (registry[sid].kind if registry and sid in registry else corpus_kind(d.name)[0])
        if kind not in MAINSTREAM_KINDS:
            continue
        for f in sorted(d.glob("*.jsonl")):
            with f.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    tk = {str(x).upper() for x in (r.get("tickers") or [])} & want
                    if not tk:
                        continue
                    ts = [parse_utc(r.get("published_utc")), parse_utc(r.get("first_seen_utc"))]
                    ts = [x for x in ts if x is not None]
                    if not ts:
                        continue
                    for k in tk:
                        rows.append({"ticker": k, "source_id": sid, "t": min(ts)})
    return pd.DataFrame(rows, columns=["ticker", "source_id", "t"])


def lead_times_h(claims: pd.DataFrame, mainstream: pd.DataFrame, *,
                 window_h: float = LEAD_WINDOW_H) -> pd.Series:
    """Hours from the claim to the earliest mainstream item on the same ticker
    within +/- window_h (positive = the source was FIRST). NaN = no match."""
    out = pd.Series(np.nan, index=claims.index, dtype=float)
    if claims.empty or mainstream is None or mainstream.empty:
        return out
    ms = mainstream.copy()
    ms["t"] = pd.to_datetime(ms["t"], utc=True)
    groups = {k: g for k, g in ms.groupby("ticker")}
    for i, r in claims.iterrows():
        g = groups.get(str(r["ticker"]).upper())
        t = parse_utc(r["claim_utc"])
        if g is None or t is None:
            continue
        ct = pd.Timestamp(t)
        lo, hi = ct - pd.Timedelta(hours=window_h), ct + pd.Timedelta(hours=window_h)
        w = g[(g["t"] >= lo) & (g["t"] <= hi) & (g["source_id"] != r.get("source_id"))]
        if len(w):
            out.at[i] = (w["t"].min() - ct).total_seconds() / 3600.0
    return out


def _source_skill(graded: pd.DataFrame) -> pd.DataFrame:
    """forecast_reputation.arm_skill keyed (source_id, observable, horizon)."""
    from backend.services import forecast_reputation as FR
    if graded is None or graded.empty:
        return pd.DataFrame()
    g = graded[graded["arm"].astype(str).str.startswith(SPECIALIST_PREFIX)].copy()
    if g.empty:
        return pd.DataFrame()
    g["source_id"] = g["arm"].astype(str).str[len(SPECIALIST_PREFIX):]
    g = g[g["observable"].astype(str) == FR.DIRECTION_OBSERVABLE]
    return FR.arm_skill(g, by=KEY_SOURCE_OBSERVABLE_HORIZON)


def _f(v: Any, nd: int = 4) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def score(registry: dict[str, Source], *, claims: list[dict] | None = None,
          ledger_rows: list[dict] | None = None, bars: pd.DataFrame | None = None,
          mainstream: pd.DataFrame | None = None,
          sector_map: dict[str, str] | None = None) -> dict:
    """The scoreboard. Every source appears; a source with no claims is n=0,
    weight=prior -- it has not earned anything yet, which is not the same as
    having earned zero."""
    from backend.services import forecast_reputation as FR
    claims = claims if claims is not None else read_claims()
    cf = pd.DataFrame(claims)
    if cf.empty:
        cf = pd.DataFrame(columns=["claim_hash", "source_id", "ticker", "claim_utc", "direction"])
    cf = cf.reset_index(drop=True)
    rel = forward_relative_returns(cf, bars)
    sign = cf["direction"].map({"up": 1.0, "down": -1.0}) if len(cf) else pd.Series(dtype=float)
    for h in (1, 5, 21):
        cf[f"rel_{h}d"] = rel[f"rel_{h}d"] if len(cf) else []
        cf[f"signed_{h}d"] = cf[f"rel_{h}d"] * sign if len(cf) else []
    cf["lead_h"] = lead_times_h(cf, mainstream) if len(cf) else []
    graded = FR.graded_frame_from_rows(ledger_rows or [])
    skill = _source_skill(graded)
    sector_map = sector_map or {}
    rows = []
    for sid, src in sorted(registry.items(), key=lambda kv: (kv[1].kind, kv[0])):
        sub = cf[cf["source_id"] == sid]
        n = int(len(sub))
        row: dict[str, Any] = {"source_id": sid, "kind": src.kind, "platform": src.platform,
                               "verified": src.verified, "n_claims": n,
                               "n_directional": int(sub["direction"].isin(["up", "down"]).sum()) if n else 0}
        lead = sub["lead_h"].dropna() if n else pd.Series(dtype=float)
        row["n_lead_matched"] = int(len(lead))
        row["corroboration_rate"] = _f(len(lead) / n) if n else None
        row["lead_h_median"] = _f(lead.median(), 2) if len(lead) else None
        row["share_led_mainstream"] = _f((lead > 0).mean()) if len(lead) else None
        for h in (1, 5, 21):
            col = sub[f"rel_{h}d"].dropna() if n else pd.Series(dtype=float)
            row[f"rel_ret_{h}d"] = _f(col.mean()) if len(col) else None
            sc = sub[f"signed_{h}d"].dropna() if n else pd.Series(dtype=float)
            row[f"signed_ret_{h}d"] = _f(sc.mean()) if len(sc) else None
        s21 = sub["signed_21d"].dropna() if n else pd.Series(dtype=float)
        row["false_positive_rate_21d"] = _f((s21 < 0).mean()) if len(s21) else None
        row["n_resolved_21d"] = int(len(s21))
        cs = crowding_signature(sub["signed_5d"].tolist() if n else [],
                                sub["signed_21d"].tolist() if n else [])
        row["crowding_signature"] = _f(cs["signature"])
        use_as = cs["use_as"]
        for h in SCORE_HORIZONS:
            key = (sid, FR.DIRECTION_OBSERVABLE, h)
            if not skill.empty and key in skill.index:
                k = skill.loc[key]
                row[f"n_graded_h{h}"] = int(k["n_total"])
                row[f"brier_h{h}"] = _f(k["brier"])
                row[f"skill_h{h}"] = _f(k["skill"])
            else:
                row[f"n_graded_h{h}"] = 0
                row[f"brier_h{h}"] = None
                row[f"skill_h{h}"] = None
        earned = [(h, row[f"skill_h{h}"]) for h in SCORE_HORIZONS
                  if row[f"n_graded_h{h}"] >= MIN_N_FOR_WEIGHT and row[f"skill_h{h}"] is not None]
        if earned:
            row["weight"] = _f(max(0.0, max(s for _, s in earned)))
            row["weight_status"] = "earned"
        else:
            row["weight"] = "prior"
            row["weight_status"] = f"prior (needs {MIN_N_FOR_WEIGHT} graded rows at a horizon)"
        if use_as == "prior" and earned:
            use_as = "attention"
        row["use_as"] = use_as
        if n:
            secs = sub["ticker"].map(lambda t: sector_map.get(str(t).upper(), "unknown"))
            vc = secs.value_counts(normalize=True)
            row["top_sector"] = str(vc.index[0])
            row["top_sector_share"] = _f(vc.iloc[0])
            row["sector_hhi"] = _f(float((vc ** 2).sum()))
        else:
            row["top_sector"] = None
            row["top_sector_share"] = None
            row["sector_hhi"] = None
        rows.append(row)
    by_kind: dict[str, dict] = {}
    for r in rows:
        k = by_kind.setdefault(r["kind"], {"n_sources": 0, "n_claims": 0, "n_unverified": 0})
        k["n_sources"] += 1
        k["n_claims"] += r["n_claims"]
        k["n_unverified"] += int(not r["verified"])
    return {"schema": "source_scoreboard/v1", "generated_at": _now(),
            "n_sources": len(rows), "n_claims": int(len(cf)),
            "n_sources_with_claims": sum(1 for r in rows if r["n_claims"]),
            "by_kind": dict(sorted(by_kind.items())),
            "contract": CLAIM_CONTRACT,
            "metrics": {
                "lead_h_median": f"hours from claim to the earliest mainstream (newswire/filing) item on the same ticker within +/-{LEAD_WINDOW_H:.0f}h; positive = source first",
                "corroboration_rate": "share of claims with a mainstream item on the same ticker in that window (a proxy for fact accuracy until facts are matched)",
                "rel_ret_Nd": "mean name-minus-SPY return over N sessions entering at the first close strictly after the claim date",
                "signed_ret_Nd": "the same, times the claim's stated direction",
                "false_positive_rate_21d": "share of directional claims whose signed 21-session relative return was negative",
                "skill_hN": "forecast_reputation.arm_skill keyed (source_id, beats_benchmark, h), held out on the later half by date",
                "crowding_signature": "mean signed 21d minus mean signed 5d; <= %.2f with a positive 5d and n >= %d = use_as reversal" % (REVERSAL_THRESHOLD, MIN_N_FOR_REVERSAL),
                "weight": f"'prior' until {MIN_N_FOR_WEIGHT} graded rows at a horizon; then max(0, best held-out skill)",
            },
            "never": "X and Reddit never generate orders. A weight here is attention, not a truth.",
            "rows": rows}


def write_scoreboard(sb: dict, *, out_dir: Path | None = None, day: str | None = None) -> tuple[Path, Path]:
    d = Path(out_dir) if out_dir else SOURCES_DIR
    d.mkdir(parents=True, exist_ok=True)
    day = day or date.today().isoformat()
    jp = d / f"scoreboard_{day}.json"
    jp.write_text(json.dumps(sb, indent=2, default=str), encoding="utf-8")
    mp = d / "SOURCES.md"
    mp.write_text(render_markdown(sb, day=day), encoding="utf-8")
    return jp, mp


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:+.4f}" if abs(v) < 10 else f"{v:.1f}"
    return str(v)


def render_markdown(sb: dict, *, day: str) -> str:
    lines = [f"# SOURCES -- the source/actor scoreboard ({day})", "",
             "Every source is a forecaster that has not earned a weight yet. Social "
             "sources are an **attention layer, not a truth layer**; X and Reddit "
             "**never generate orders**. A source whose names pop then fade is kept "
             "and labelled `use_as: reversal`.", "",
             f"Receipt: `scoreboard_{day}.json` -- {sb['n_sources']} sources, "
             f"{sb['n_claims']} claims, {sb['n_sources_with_claims']} sources with at "
             f"least one claim.", "", "## By kind", "",
             "| kind | sources | claims | unverified |", "|---|---:|---:|---:|"]
    for k, v in sb["by_kind"].items():
        lines.append(f"| {k} | {v['n_sources']} | {v['n_claims']} | {v['n_unverified']} |")
    lines += ["", "## Sources with claims (or social, unverified or not)", "",
              "| source | kind | verified | n | lead h (med) | corrob. | 1d | 5d | 21d signed | FP 21d | skill h1/h5/h20 | crowding | weight | use as |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|"]
    shown = [r for r in sb["rows"] if r["n_claims"] or r["platform"] in SOCIAL_PLATFORMS]
    for r in shown:
        sk = "/".join(_fmt(r.get(f"skill_h{h}")) for h in SCORE_HORIZONS)
        lines.append(
            f"| {r['source_id']} | {r['kind']} | {r['verified']} | {r['n_claims']} | "
            f"{_fmt(r['lead_h_median'])} | {_fmt(r['corroboration_rate'])} | "
            f"{_fmt(r['rel_ret_1d'])} | {_fmt(r['rel_ret_5d'])} | {_fmt(r['signed_ret_21d'])} | "
            f"{_fmt(r['false_positive_rate_21d'])} | {sk} | {_fmt(r['crowding_signature'])} | "
            f"{r['weight']} | {r['use_as']} |")
    if not shown:
        lines.append("| (none: no claim recorded and no X/Reddit source registered yet) "
                     "| | | | | | | | | | | | | |")
    n_rest = len(sb["rows"]) - len(shown)
    lines += ["", f"{n_rest} further registered sources (newswires, filings, "
              f"brokerages) have n=0 and weight=prior; they are in the JSON receipt.",
              "", "## Metrics", ""]
    for k, v in sb["metrics"].items():
        lines.append(f"- `{k}`: {v}")
    return "\n".join(lines) + "\n"


def sector_map_default() -> dict[str, str]:
    """ticker -> sector from config's stock universe; unknown names are 'unknown'."""
    try:
        from backend.services.attribution import _build_sector_map
        return {str(k).upper(): v for k, v in _build_sector_map().items()}
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("source_registry: sector map unavailable (%s)", exc)
        return {}
