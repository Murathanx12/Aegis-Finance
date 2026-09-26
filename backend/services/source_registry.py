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
    #: None = prior (nothing earned yet). A number is an EARNED weight and
    #: `weight_basis` says from what (e.g. the broker scoreboard's held-out 21d
    #: hit-rate skill, shrunk n/(n+200)).
    weight: float | None = None
    weight_basis: str = ""

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
        found_by_quest=str(d.get("found_by_quest") or ""), notes=str(d.get("notes") or ""),
        weight=_opt_float(d.get("weight")), weight_basis=str(d.get("weight_basis") or ""))


def _opt_float(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


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
    md = render_markdown(sb, day=day)
    if sb.get("brokers"):
        md += "\n" + render_broker_markdown(sb["brokers"], day=day)
    mp.write_text(md, encoding="utf-8")
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
              f"brokerages) have no claims in the claims ledger; they are in the JSON "
              f"receipt. Brokerages are scored from the revisions parquet below "
              f"(`brokers` in the receipt) when that section is present.",
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


# ═════════════════════════════ the broker scoreboard ════════════════════════
#
# Adjudication 2026-09-26 row 13 (reviewer A+B+F, W4): the 456 brokerages were
# registered at n=0 while `target_revisions.parquet` already held ~393k dated,
# directional claims. Scoring them costs $0 and needs no LLM:
#   * a claim = one revision row; direction = target Raises/Lowers, else a
#     rating up/down; a row that raises the target AND downgrades is MIXED and
#     is not a directional claim (it is still counted);
#   * entry = the close of the first session STRICTLY after the event date (a
#     revision stamped during a session is not assumed tradable at its close);
#   * outcome = the name's h-session return minus the UNIVERSE MEDIAN h-session
#     return from the same entry session, over the survivorship-free panel;
#   * hit = the signed relative return is > 0;
#   * first-mover vs follower: a cluster is >= 3 distinct firms moving the same
#     name in the same direction within 10 calendar days of the cluster's first
#     claim; the first firm's signed return from ITS entry is compared with the
#     last firm's from ITS entry, per cluster, blocked by month.
# Rows dated after `today` or after their own `pulled_at` are refused (one
# AMR/Jefferies row is dated 2026-10-05 and was pulled 2026-09-25).

BROKER_HORIZONS: tuple[int, ...] = (5, 21)
BROKER_CLUSTER_DAYS: int = int(_cfg("BROKER_CLUSTER_DAYS", 10))
BROKER_CLUSTER_MIN_FIRMS: int = int(_cfg("BROKER_CLUSTER_MIN_FIRMS", 3))
BROKER_RANK_MIN_N: int = int(_cfg("BROKER_RANK_MIN_N", 50))
BROKER_RANK_YEARS: int = int(_cfg("BROKER_RANK_YEARS", 3))
BROKER_WEIGHT_MIN_N: int = int(_cfg("BROKER_WEIGHT_MIN_N", 20))
BROKER_SHRINK_K: float = float(_cfg("BROKER_SHRINK_K", 200.0))
#: a corpus row published this long before we first saw it is an archive
#: backfill (the 36,720-row benzinga archive, adjudication row 12), not news.
ARCHIVE_GAP_DAYS: int = int(_cfg("SOURCE_ARCHIVE_GAP_DAYS", 30))
#: calendar days between the day after a claim and its entry session; more =
#: the claim predates the panel (or sits in a gap) and is left unpriced.
MAX_ENTRY_GAP_DAYS: int = 6


def broker_direction(target_action: Any, action: Any) -> str | None:
    """'up' / 'down' / None (no directional content, or MIXED signals)."""
    ta = str(target_action or "").strip().lower()
    ac = str(action or "").strip().lower()
    ups = (ta == "raises") + (ac == "up")
    downs = (ta == "lowers") + (ac == "down")
    if ups and not downs:
        return "up"
    if downs and not ups:
        return "down"
    return None


def load_revision_claims(path: Path | str | None = None, *, today: Any = None) -> tuple[pd.DataFrame, dict]:
    """The revisions parquet as claims: ticker, firm, source_id, t (UTC-naive
    timestamp), direction. Refuses future-dated rows and rows dated after their
    own pull; the receipt counts both."""
    p = Path(path) if path else TARGET_REVISIONS
    df = pd.read_parquet(p)
    cols = ["ticker", "event_date", "firm", "target_action", "action", "pulled_at"]
    df = df[[c for c in cols if c in df.columns]].copy()
    today_end = pd.Timestamp(today or date.today()).normalize() + pd.Timedelta(days=1)
    t = pd.to_datetime(df["event_date"], errors="coerce", utc=True).dt.tz_localize(None)
    rc = {"n_rows": int(len(df)), "n_undated": int(t.isna().sum())}
    fut = (t >= today_end).fillna(False)
    if "pulled_at" in df.columns:
        pulled = pd.to_datetime(df["pulled_at"], errors="coerce", utc=True).dt.tz_localize(None)
        after_pull = (t > pulled).fillna(False)
    else:
        after_pull = pd.Series(False, index=df.index)
    rc["n_refused_future"] = int(fut.sum())
    rc["n_refused_after_pull"] = int((after_pull & ~fut).sum())
    keep = t.notna() & ~fut & ~after_pull
    df = df[keep].copy()
    df["t"] = t[keep]
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["firm"] = df["firm"].astype(str)
    df["source_id"] = "sell_side:" + df["firm"].map(_slug)
    ta = df["target_action"] if "target_action" in df.columns else pd.Series("", index=df.index)
    ac = df["action"] if "action" in df.columns else pd.Series("", index=df.index)
    df["direction"] = [broker_direction(a, b) for a, b in zip(ta, ac)]
    df = df[df["firm"].map(_slug) != ""]
    rc["n_claims"] = int(len(df))
    rc["n_directional"] = int(df["direction"].notna().sum())
    rc["n_firms"] = int(df["source_id"].nunique())
    return df[["ticker", "firm", "source_id", "t", "direction"]].reset_index(drop=True), rc


def load_close_panel(paths: Sequence[Path] | None = None) -> pd.DataFrame:
    """Long symbol/date/close from the survivorship-free panel.

    Same semantics as `xs_ranker.load_bars(survivorship_free_paths())` --
    concatenate, keep a (symbol, date)'s FIRST occurrence (the living pull over
    the delisted one) -- but reads three columns, not nine: the full load peaks
    well above the ~4 GB this machine had free on 2026-09-26."""
    from backend.services import xs_ranker as X
    ps = list(paths) if paths is not None else X.survivorship_free_paths()
    frames = []
    for p in ps:
        f = pd.read_parquet(p, columns=["symbol", "date", "close"])
        f["close"] = f["close"].astype("float32")
        frames.append(f)
    out = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    out["symbol"] = out["symbol"].astype(str)
    out["date"] = pd.to_datetime(out["date"])
    return out.drop_duplicates(subset=["symbol", "date"], keep="first")


def relative_forward_returns(bars_long: pd.DataFrame, horizons: Sequence[int] = BROKER_HORIZONS
                             ) -> tuple[pd.DatetimeIndex, list[str], dict[int, np.ndarray]]:
    """(dates, symbols, {h: rel}) where rel[i, j] = symbol j's return from the
    close of session i to session i+h, minus the cross-sectional MEDIAN of that
    return over every symbol priced on both sessions."""
    import warnings
    px = bars_long.pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
    px = px.sort_index()
    arr = px.to_numpy(dtype="float32")
    arr[~np.isfinite(arr) | (arr <= 0)] = np.nan
    out: dict[int, np.ndarray] = {}
    for h in horizons:
        fwd = np.full_like(arr, np.nan)
        if len(arr) > h:
            fwd[:-h] = arr[h:] / arr[:-h] - 1.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(fwd, axis=1)
        out[h] = fwd - med[:, None]
        del fwd
    return pd.DatetimeIndex(px.index), [str(c) for c in px.columns], out


def attach_outcomes(claims: pd.DataFrame, dates: pd.DatetimeIndex, symbols: list[str],
                    rel: dict[int, np.ndarray]) -> pd.DataFrame:
    """Adds entry (session), rel_{h}d, signed_{h}d and hit_{h}d to each claim."""
    c = claims.copy()
    col = {s: i for i, s in enumerate(symbols)}
    j = c["ticker"].map(col)
    day0 = c["t"].dt.normalize() + pd.Timedelta(days=1)
    pos = dates.searchsorted(day0)
    ok = j.notna().to_numpy() & (pos < len(dates))
    # a claim before the panel starts (or inside a gap) must not be priced at
    # the panel's first session: the entry must fall within a week of the claim
    gap = np.full(len(c), np.inf)
    gap[ok] = (dates.to_numpy()[pos[ok]] - day0.to_numpy()[ok]) / np.timedelta64(1, "D")
    ok &= gap <= MAX_ENTRY_GAP_DAYS
    entry = np.full(len(c), np.datetime64("NaT"), dtype="datetime64[ns]")
    entry[ok] = dates.to_numpy()[pos[ok]]
    c["entry"] = entry
    sign = c["direction"].map({"up": 1.0, "down": -1.0}).to_numpy(dtype=float)
    ji = j.fillna(-1).astype(int).to_numpy()
    for h, m in rel.items():
        v = np.full(len(c), np.nan)
        v[ok] = m[pos[ok], ji[ok]]
        s = v * sign
        c[f"rel_{h}d"] = v
        c[f"signed_{h}d"] = s
        c[f"hit_{h}d"] = np.where(np.isfinite(s), (s > 0).astype(float), np.nan)
    return c


def assign_clusters(claims: pd.DataFrame, *, days: int = BROKER_CLUSTER_DAYS,
                    min_firms: int = BROKER_CLUSTER_MIN_FIRMS) -> pd.DataFrame:
    """Directional claims with cluster_id, cluster_rank (1 = first firm),
    cluster_size (distinct firms). A firm's repeat inside its cluster is dropped
    (its first claim is its position). Clusters with < min_firms are dropped."""
    d = claims[claims["direction"].notna()].sort_values(["ticker", "direction", "t", "source_id"],
                                                         kind="mergesort")
    cid = np.full(len(d), -1, dtype=np.int64)
    tk = d["ticker"].to_numpy()
    dr = d["direction"].to_numpy()
    tt = d["t"].to_numpy()
    span = np.timedelta64(days, "D")
    cur, start, key = -1, None, None
    for i in range(len(d)):
        k = (tk[i], dr[i])
        if k != key or tt[i] > start + span:
            cur += 1
            key, start = k, tt[i]
        cid[i] = cur
    d = d.assign(cluster_id=cid)
    d = d.drop_duplicates(subset=["cluster_id", "source_id"], keep="first")
    size = d.groupby("cluster_id")["source_id"].transform("size")
    d = d[size >= min_firms].copy()
    d["cluster_size"] = d.groupby("cluster_id")["source_id"].transform("size")
    d["cluster_rank"] = d.groupby("cluster_id").cumcount() + 1
    return d


def _block_mean_se(values: pd.Series, blocks: pd.Series) -> dict:
    v = pd.DataFrame({"v": values, "b": blocks}).dropna()
    if v.empty:
        return {"n": 0, "n_blocks": 0, "mean": None, "block_mean": None,
                "se_block": None, "t_block": None}
    bm = v.groupby("b")["v"].mean()
    nb = len(bm)
    se = float(bm.std(ddof=1) / math.sqrt(nb)) if nb > 1 else None
    return {"n": int(len(v)), "n_blocks": int(nb), "mean": _f(v["v"].mean(), 5),
            "block_mean": _f(bm.mean(), 5), "se_block": _f(se, 5),
            "t_block": _f(bm.mean() / se, 2) if se else None}


def first_mover_table(clustered: pd.DataFrame, *, h: int = 21) -> dict:
    """First firm vs last firm in the same cluster: paired, month-blocked."""
    col = f"signed_{h}d"
    if clustered.empty:
        return {"horizon": h, "n_clusters": 0}
    first = clustered[clustered["cluster_rank"] == 1].set_index("cluster_id")
    last = clustered[clustered["cluster_rank"] == clustered["cluster_size"]].set_index("cluster_id")
    pair = first[[col, "t", "entry"]].join(last[[col, "entry"]], rsuffix="_last", how="inner")
    pair["diff"] = pair[col] - pair[f"{col}_last"]
    pair["block"] = pair["t"].dt.to_period("M").astype(str)
    pair["year"] = pair["t"].dt.year
    staggered = pair[pair["entry_last"] > pair["entry"]]
    by_rank = {}
    rk = clustered["cluster_rank"].clip(upper=5)
    for r, g in clustered.groupby(rk):
        s = g[col].dropna()
        by_rank["5+" if r == 5 else str(int(r))] = {
            "n": int(len(s)), "mean_signed": _f(s.mean(), 5),
            "hit": _f((s > 0).mean(), 4) if len(s) else None}
    by_year, loyo = {}, []
    for y, g in staggered.groupby("year"):
        by_year[str(int(y))] = {"n": int(g["diff"].notna().sum()), "mean_diff": _f(g["diff"].mean(), 5)}
        rest = staggered[staggered["year"] != y]["diff"].dropna()
        if len(rest):
            loyo.append(float(rest.mean()))
    return {"horizon": h, "n_clusters": int(len(pair)),
            "n_staggered": int(len(staggered)),
            "share_same_session": _f(1 - len(staggered) / len(pair), 4) if len(pair) else None,
            "first_mean_signed": _f(pair[col].mean(), 5),
            "last_mean_signed": _f(pair[f"{col}_last"].mean(), 5),
            "first_minus_last_all": _block_mean_se(pair["diff"], pair["block"]),
            "first_minus_last_staggered": _block_mean_se(staggered["diff"], staggered["block"]),
            "staggered_first_mean_signed": _f(staggered[col].mean(), 5),
            "staggered_last_mean_signed": _f(staggered[f"{col}_last"].mean(), 5),
            "staggered_by_year": by_year,
            "staggered_leave_one_year_out_worst": _f(min(loyo), 5) if loyo else None,
            "by_rank": by_rank,
            "read": ("diff = first firm's signed relative return from its own entry minus the "
                     "last firm's from its own entry, same cluster. 'staggered' keeps clusters "
                     "whose last firm entered on a LATER session (same-session ties have diff 0 "
                     "by construction). Blocks = calendar month of the cluster's first claim.")}


def prior_firm_counts(claims: pd.DataFrame, *, days: int = BROKER_CLUSTER_DAYS) -> pd.Series:
    """For each directional claim: how many OTHER firms made a claim in the same
    direction on the same name in the `days` calendar days strictly before it.
    Point-in-time: uses only earlier claims, so 0 = 'first' is knowable at t."""
    d = claims[claims["direction"].notna()].sort_values(["ticker", "direction", "t"], kind="mergesort")
    tk, dr, tt, sid = (d["ticker"].to_numpy(), d["direction"].to_numpy(),
                       d["t"].to_numpy(), d["source_id"].to_numpy())
    span = np.timedelta64(days, "D")
    out = np.zeros(len(d), dtype=np.int64)
    n = len(d)
    lo, key, counts = 0, None, {}
    i = 0
    while i < n:
        k = (tk[i], dr[i])
        if k != key:
            key, lo, counts = k, i, {}
        # the block of rows sharing this exact timestamp: none is "prior" to another
        j = i
        while j + 1 < n and tk[j + 1] == tk[i] and dr[j + 1] == dr[i] and tt[j + 1] == tt[i]:
            j += 1
        while lo < i and tt[lo] < tt[i] - span:
            f = sid[lo]
            counts[f] -= 1
            if counts[f] == 0:
                del counts[f]
            lo += 1
        for q in range(i, j + 1):
            out[q] = len(counts) - (1 if sid[q] in counts else 0)
        for q in range(i, j + 1):
            counts[sid[q]] = counts.get(sid[q], 0) + 1
        i = j + 1
    return pd.Series(out, index=d.index).reindex(claims.index)


def pit_first_vs_follower(claims: pd.DataFrame, *, days: int = BROKER_CLUSTER_DAYS) -> dict:
    """The TRADABLE version of first-mover vs follower. Each claim is classed by
    what was knowable at its own time: 'first' (no other firm moved the name
    the same way in the prior `days`), 'second', 'third_plus'. The cluster table
    conditions on followers arriving LATER, which is look-ahead; this does not."""
    c = claims[claims["direction"].notna()].copy()
    c["n_prior"] = prior_firm_counts(claims, days=days).reindex(c.index)
    c["grp"] = np.where(c["n_prior"] == 0, "first", np.where(c["n_prior"] == 1, "second", "third_plus"))
    c["block"] = c["t"].dt.to_period("M").astype(str)
    out: dict[str, Any] = {"window_days": days,
                           "read": "class = other firms moving the name the same way in the prior "
                                   f"{days} days (knowable at t). diff = month-mean(first) - "
                                   "month-mean(third_plus), blocked by month."}
    for h in BROKER_HORIZONS:
        col = f"signed_{h}d"
        groups = {}
        for g, gg in c.groupby("grp"):
            s = gg[col].dropna()
            groups[g] = {"n": int(len(s)), "mean_signed": _f(s.mean(), 5),
                         "hit": _f((s > 0).mean(), 4) if len(s) else None}
        m = c.dropna(subset=[col]).groupby(["block", "grp"])[col].mean().unstack()
        res: dict[str, Any] = {"by_class": groups}
        if {"first", "third_plus"} <= set(m.columns):
            dm = (m["first"] - m["third_plus"]).dropna()
            se = float(dm.std(ddof=1) / math.sqrt(len(dm))) if len(dm) > 1 else None
            res["first_minus_third_plus"] = {"n_blocks": int(len(dm)), "mean": _f(dm.mean(), 5),
                                             "se_block": _f(se, 5),
                                             "t_block": _f(dm.mean() / se, 2) if se else None}
            yr = dm.groupby(dm.index.str[:4]).mean()
            res["by_year"] = {y: _f(v, 5) for y, v in yr.items()}
            res["leave_one_year_out_worst"] = _f(min(dm[dm.index.str[:4] != y].mean() for y in yr.index), 5) \
                if len(yr) > 1 else None
        out[str(h)] = res
    return out


def firm_first_mover_rows(clustered: pd.DataFrame, *, since: pd.Timestamp, h: int = 21,
                          min_n: int = 30) -> list[dict]:
    c = clustered[clustered["t"] >= since]
    col = f"signed_{h}d"
    out = []
    for sid, g in c.groupby("source_id"):
        if len(g) < min_n:
            continue
        f = g[g["cluster_rank"] == 1]
        fo = g[g["cluster_rank"] > 1]
        out.append({"source_id": sid, "firm": str(g["firm"].iloc[0]),
                    "n_cluster_claims": int(len(g)), "n_first": int(len(f)),
                    "share_first": _f(len(f) / len(g), 4),
                    "mean_rank_pct": _f(((g["cluster_rank"] - 1) / (g["cluster_size"] - 1)).mean(), 4),
                    "signed_when_first": _f(f[col].mean(), 5),
                    "signed_when_follower": _f(fo[col].mean(), 5)})
    out.sort(key=lambda r: -(r["share_first"] or 0))
    return out


def _hit_stats(g: pd.DataFrame) -> dict:
    d = g[g["direction"].notna()]
    r = {"n_claims": int(len(g)), "n_directional": int(len(d))}
    for h in BROKER_HORIZONS:
        hh = d[f"hit_{h}d"].dropna()
        r[f"n_resolved_{h}d"] = int(len(hh))
        r[f"hit_{h}d"] = _f(hh.mean(), 4) if len(hh) else None
        up = d.loc[d["direction"] == "up", f"rel_{h}d"].dropna()
        dn = d.loc[d["direction"] == "down", f"rel_{h}d"].dropna()
        r[f"rel_{h}d_after_raise"] = _f(up.mean(), 5) if len(up) else None
        r[f"rel_{h}d_after_lower"] = _f(dn.mean(), 5) if len(dn) else None
        r[f"n_raise_{h}d"] = int(len(up))
        r[f"n_lower_{h}d"] = int(len(dn))
    return r


def broker_lead_times(claims: pd.DataFrame, mainstream: pd.DataFrame | None) -> pd.Series:
    """Hours from the revision to the first mainstream corpus item on the same
    ticker within +/- LEAD_WINDOW_H; NaN where the corpus does not cover the
    name or the date (the corpus starts 2026-09-11)."""
    empty = pd.Series(np.nan, index=claims.index, dtype=float)
    if mainstream is None or mainstream.empty or claims.empty:
        return empty
    lo = pd.to_datetime(mainstream["t"], utc=True).min().tz_localize(None) - pd.Timedelta(hours=LEAD_WINDOW_H)
    sub = claims[(claims["t"] >= lo) & claims["ticker"].isin(set(mainstream["ticker"]))]
    if sub.empty:
        return empty
    tmp = pd.DataFrame({"ticker": sub["ticker"], "source_id": sub["source_id"],
                        "claim_utc": sub["t"].dt.tz_localize("UTC")}, index=sub.index)
    return lead_times_h(tmp, mainstream).reindex(claims.index)


def broker_scoreboard(claims: pd.DataFrame, *, today: Any = None,
                      mainstream: pd.DataFrame | None = None,
                      rank_years: int = BROKER_RANK_YEARS, rank_min_n: int = BROKER_RANK_MIN_N,
                      weight_min_n: int = BROKER_WEIGHT_MIN_N, shrink_k: float = BROKER_SHRINK_K,
                      top_n: int = 20) -> dict:
    """Per firm and per year from claims that already carry outcomes
    (`attach_outcomes`). Pure: no disk, no network."""
    today_ts = pd.Timestamp(today or date.today()).normalize()
    since = today_ts - pd.DateOffset(years=rank_years)
    c = claims.copy()
    c["year"] = c["t"].dt.year
    c["lead_h"] = broker_lead_times(c, mainstream)
    recent = c[c["t"] >= since]
    # held-out split: ONE global date (the median resolved directional claim in
    # the window), so no firm's held-out half overlaps another's training half.
    rd = recent[recent["direction"].notna() & recent["hit_21d"].notna()]
    split = rd["t"].quantile(0.5) if len(rd) else today_ts
    firms = []
    for sid, g in c.groupby("source_id"):
        row = {"source_id": sid, "firm": str(g["firm"].value_counts().index[0]),
               "first_claim": str(g["t"].min().date()), "last_claim": str(g["t"].max().date())}
        row.update(_hit_stats(g))
        gr = g[g["t"] >= since]
        row.update({f"recent_{k}": v for k, v in _hit_stats(gr).items()})
        by_year = {}
        for y, gy in g.groupby("year"):
            hy = gy[gy["direction"].notna()]["hit_21d"].dropna()
            by_year[str(int(y))] = {"n": int(len(hy)), "hit_21d": _f(hy.mean(), 3) if len(hy) else None}
        row["by_year"] = by_year
        dd = gr[gr["direction"].notna() & gr["hit_21d"].notna()]
        ins, held = dd[dd["t"] < split], dd[dd["t"] >= split]
        row["n_insample_21d"] = int(len(ins))
        row["n_heldout_21d"] = int(len(held))
        row["skill_insample_21d"] = _f(2 * ins["hit_21d"].mean() - 1, 4) if len(ins) else None
        row["skill_heldout_21d"] = _f(2 * held["hit_21d"].mean() - 1, 4) if len(held) else None
        n = len(held)
        if n >= weight_min_n and row["skill_heldout_21d"] is not None:
            shrunk = row["skill_heldout_21d"] * n / (n + shrink_k)
            row["skill_heldout_21d_shrunk"] = _f(shrunk, 5)
            row["weight"] = _f(max(0.0, shrunk), 5)
            row["weight_status"] = "earned"
        else:
            row["skill_heldout_21d_shrunk"] = None
            row["weight"] = "prior"
            row["weight_status"] = f"prior (held-out n={n} < {weight_min_n})"
        lead = g["lead_h"].dropna()
        row["n_lead_matched"] = int(len(lead))
        row["lead_h_median"] = _f(lead.median(), 2) if len(lead) else None
        row["share_led_mainstream"] = _f((lead > 0).mean(), 3) if len(lead) else None
        firms.append(row)
    ranked = [r for r in firms if r["recent_n_resolved_21d"] >= rank_min_n
              and r["recent_hit_21d"] is not None]
    ranked.sort(key=lambda r: (-r["recent_hit_21d"], r["source_id"]))
    by_year_all = {str(int(y)): _hit_stats(gy) for y, gy in c.groupby("year")}
    # persistence: does in-sample skill predict held-out skill across firms?
    pers = [(r["skill_insample_21d"], r["skill_heldout_21d"]) for r in firms
            if r["n_insample_21d"] >= weight_min_n and r["n_heldout_21d"] >= weight_min_n]
    rho = None
    if len(pers) >= 5:
        a = np.array(pers, float)
        rho = float(pd.Series(a[:, 0]).rank().corr(pd.Series(a[:, 1]).rank()))
    clustered = assign_clusters(c)
    base = c[c["direction"].notna()]
    rbase = recent[recent["direction"].notna()]
    return {"schema": "broker_scoreboard/v1", "generated_at": _now(),
            "asof": str(today_ts.date()), "rank_window_since": str(since.date()),
            "heldout_split_date": str(pd.Timestamp(split).date()),
            "n_claims": int(len(c)), "n_directional": int(len(base)),
            "n_firms": len(firms), "n_ranked": len(ranked),
            "base_rate": {f"hit_{h}d": _f(base[f"hit_{h}d"].mean(), 4) for h in BROKER_HORIZONS},
            "base_rate_recent": {f"hit_{h}d": _f(rbase[f"hit_{h}d"].mean(), 4) for h in BROKER_HORIZONS},
            "persistence_insample_vs_heldout_spearman": _f(rho, 3) if rho is not None else None,
            "n_firms_persistence": len(pers),
            "n_weight_earned": sum(1 for r in firms if r["weight_status"] == "earned"),
            "top": [r["source_id"] for r in ranked[:top_n]],
            "bottom": [r["source_id"] for r in ranked[::-1][:top_n]],
            "by_year": by_year_all,
            "first_mover_pit": pit_first_vs_follower(c),
            "first_mover": {str(h): first_mover_table(clustered, h=h) for h in BROKER_HORIZONS},
            "first_mover_note": ("`first_mover` (clusters) conditions on >= 3 firms arriving, i.e. on "
                                 "the FUTURE: descriptive only. `first_mover_pit` classes each claim by "
                                 "what was knowable at its own time and is the tradable comparison."),
            "first_mover_by_firm": firm_first_mover_rows(clustered, since=since),
            "metrics": {
                "hit_Nd": "share of directional claims whose name beat the universe-median N-session return (sign agreed with the claim), entry at the first close strictly after the revision date",
                "rel_Nd_after_raise/lower": "mean name-minus-universe-median N-session return after a raise / a lower (unsigned)",
                "skill_heldout_21d": "2*hit_21d - 1 on the firm's claims dated on/after heldout_split_date within the rank window",
                "weight": f"max(0, skill_heldout_21d * n/(n+{shrink_k:.0f})) when held-out n >= {weight_min_n}; else prior",
                "lead_h_median": f"hours from the revision to the first mainstream corpus item on the name within +/-{LEAD_WINDOW_H:.0f}h (positive = broker first); null where the corpus (from 2026-09-11) has nothing",
                "caveat": "claims on the same name and day are NOT independent (a print draws 10 firms at once); hit rates are descriptive and the month-blocked first-mover SE is the only inferential number here"},
            "firms": firms}


def load_mainstream_pit(tickers: Iterable[str], *, corpus_dir: Path | None = None,
                        registry: dict[str, Source] | None = None) -> pd.DataFrame:
    """`load_mainstream_items`, minus archive backfill rows (published more than
    ARCHIVE_GAP_DAYS before first seen -- adjudication row 12)."""
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
                    pub, seen = parse_utc(r.get("published_utc")), parse_utc(r.get("first_seen_utc"))
                    if pub is not None and seen is not None and (seen - pub) > timedelta(days=ARCHIVE_GAP_DAYS):
                        continue
                    ts = [x for x in (pub, seen) if x is not None]
                    if not ts:
                        continue
                    for k in tk:
                        rows.append({"ticker": k, "source_id": sid, "t": min(ts)})
    return pd.DataFrame(rows, columns=["ticker", "source_id", "t"])


def apply_broker_weights(reg: dict[str, Source], board: dict) -> tuple[dict[str, Source], dict]:
    """Write each scored firm's weight into its registry entry. A firm with too
    few held-out claims is set back to prior (None) -- never left at a stale number."""
    out = dict(reg)
    res = {"n_earned": 0, "n_prior": 0, "n_not_in_registry": 0}
    for r in board.get("firms", []):
        sid = r["source_id"]
        if sid not in out:
            res["n_not_in_registry"] += 1
            continue
        if r["weight_status"] == "earned":
            out[sid] = replace(out[sid], weight=float(r["weight"]), weight_basis=(
                f"broker_scoreboard {board['asof']}: held-out 21d hit skill "
                f"{r['skill_heldout_21d']:+.4f} on n={r['n_heldout_21d']} (claims >= "
                f"{board['heldout_split_date']}), shrunk n/(n+{BROKER_SHRINK_K:.0f}), floored at 0"))
            res["n_earned"] += 1
        else:
            out[sid] = replace(out[sid], weight=None, weight_basis=f"prior: {r['weight_status']}")
            res["n_prior"] += 1
    return out, res


def _p(v: Any, pct: bool = False) -> str:
    if v is None:
        return "-"
    if isinstance(v, str):
        return v
    return f"{100 * v:+.2f}%" if pct else f"{v:.3f}"


def render_broker_markdown(board: dict, *, day: str) -> str:
    firms = {r["source_id"]: r for r in board["firms"]}
    L = [f"## Brokerages -- scored from `target_revisions.parquet` ({day})", "",
         f"{board['n_claims']:,} claims ({board['n_directional']:,} directional) from "
         f"{board['n_firms']} firms. Outcome = the name's return minus the universe-median "
         f"return from the first close after the revision (survivorship-free panel). "
         f"Base hit rate: 5d {_p(board['base_rate']['hit_5d'])}, 21d "
         f"{_p(board['base_rate']['hit_21d'])} (last {BROKER_RANK_YEARS}y: "
         f"{_p(board['base_rate_recent']['hit_21d'])}). Held-out split "
         f"{board['heldout_split_date']}; persistence of firm skill (Spearman, in-sample vs "
         f"held-out, {board['n_firms_persistence']} firms): "
         f"{_p(board['persistence_insample_vs_heldout_spearman'])}. "
         f"{board['n_weight_earned']} firms earned a registry weight.", "",
         f"**Caveat:** {board['metrics']['caveat']}.", ""]

    def table(ids: list[str], title: str) -> None:
        L.extend([f"### {title} (n >= {BROKER_RANK_MIN_N} resolved 21d claims since "
                  f"{board['rank_window_since']})", "",
                  "| firm | n21 | hit 21d | hit 5d | 21d after raise | 21d after lower | held-out skill (n) | weight | by year (hit21, n) |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---|"])
        for sid in ids:
            r = firms[sid]
            yrs = ", ".join(f"{y}: {_p(v['hit_21d'])} ({v['n']})" for y, v in r["by_year"].items()
                            if int(y) >= int(board["rank_window_since"][:4]) and v["n"])
            L.append(f"| {r['firm']} | {r['recent_n_resolved_21d']} | {_p(r['recent_hit_21d'])} | "
                     f"{_p(r['recent_hit_5d'])} | {_p(r['recent_rel_21d_after_raise'], True)} | "
                     f"{_p(r['recent_rel_21d_after_lower'], True)} | "
                     f"{_p(r['skill_heldout_21d'])} ({r['n_heldout_21d']}) | {_p(r['weight'])} | {yrs} |")
        L.append("")

    table(board["top"], "Top 20 by 21d hit rate")
    table(board["bottom"], "Bottom 20 by 21d hit rate")
    L += ["### All firms by year", "",
          "| year | claims | directional | hit 5d | hit 21d | 21d after raise | 21d after lower |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for y, v in board["by_year"].items():
        L.append(f"| {y} | {v['n_claims']:,} | {v['n_directional']:,} | {_p(v['hit_5d'])} | "
                 f"{_p(v['hit_21d'])} | {_p(v['rel_21d_after_raise'], True)} | "
                 f"{_p(v['rel_21d_after_lower'], True)} |")
    pit = board.get("first_mover_pit") or {}
    L += ["", f"### First mover vs follower, point-in-time (other firms moving the name the "
          f"same way in the prior {pit.get('window_days', BROKER_CLUSTER_DAYS)} days, knowable at t)", "",
          "| horizon | first: mean signed (hit, n) | second | third+ | first - third+ (month-block SE, t, blocks) | LOYO worst |",
          "|---|---|---|---|---|---:|"]
    for h in BROKER_HORIZONS:
        r = pit.get(str(h)) or {}
        bc = r.get("by_class") or {}
        cell = lambda g: (f"{_p((bc.get(g) or {}).get('mean_signed'), True)} "
                          f"({_p((bc.get(g) or {}).get('hit'))}, {(bc.get(g) or {}).get('n', 0):,})")
        d = r.get("first_minus_third_plus") or {}
        L.append(f"| {h}d | {cell('first')} | {cell('second')} | {cell('third_plus')} | "
                 f"{_p(d.get('mean'), True)} ({_p(d.get('se_block'), True)}, t {d.get('t_block')}, "
                 f"{d.get('n_blocks')}) | {_p(r.get('leave_one_year_out_worst'), True)} |")
    if pit.get("21", {}).get("by_year"):
        L.append("")
        L.append("21d first - third+ by year: " + ", ".join(
            f"{y}: {_p(v, True)}" for y, v in pit["21"]["by_year"].items()))
    L += ["", f"### First mover vs follower, clusters (>= {BROKER_CLUSTER_MIN_FIRMS} firms, "
          f"same name and direction, within {BROKER_CLUSTER_DAYS} days) -- LOOK-AHEAD, descriptive", "",
          "A cluster is only known once its followers arrive, so 'the first firm of a cluster' "
          "is selected on the future. Read this as where in a cascade the return accrues, "
          "not as a signal.", ""]
    for h, fm in board["first_mover"].items():
        if not fm.get("n_clusters"):
            continue
        a, s = fm["first_minus_last_all"], fm["first_minus_last_staggered"]
        L.append(f"- **{h}d**: {fm['n_clusters']:,} clusters; {_p(fm['share_same_session'])} have "
                 f"first and last entering on the same session. All: first "
                 f"{_p(fm['first_mean_signed'], True)} vs last {_p(fm['last_mean_signed'], True)}, "
                 f"diff {_p(a['block_mean'], True)} (month-block SE {_p(a['se_block'], True)}, "
                 f"t {a['t_block']}, {a['n_blocks']} blocks). Staggered only ({fm['n_staggered']:,}): "
                 f"first {_p(fm['staggered_first_mean_signed'], True)} vs last "
                 f"{_p(fm['staggered_last_mean_signed'], True)}, diff {_p(s['block_mean'], True)} "
                 f"(SE {_p(s['se_block'], True)}, t {s['t_block']}); leave-one-year-out worst "
                 f"{_p(fm['staggered_leave_one_year_out_worst'], True)}.")
        L.append("  - by rank: " + ", ".join(
            f"#{k}: {_p(v['mean_signed'], True)} (hit {_p(v['hit'])}, n {v['n']:,})"
            for k, v in fm["by_rank"].items()))
        L.append("  - staggered diff by year: " + ", ".join(
            f"{y}: {_p(v['mean_diff'], True)} ({v['n']})" for y, v in fm["staggered_by_year"].items()))
    fb = board.get("first_mover_by_firm") or []
    if fb:
        L += ["", f"#### Firms most often first (>= 30 cluster claims since {board['rank_window_since']})", "",
              "| firm | cluster claims | share first | mean rank pct | 21d signed when first | when follower |",
              "|---|---:|---:|---:|---:|---:|"]
        for r in fb[:15]:
            L.append(f"| {r['firm']} | {r['n_cluster_claims']} | {_p(r['share_first'])} | "
                     f"{_p(r['mean_rank_pct'])} | {_p(r['signed_when_first'], True)} | "
                     f"{_p(r['signed_when_follower'], True)} |")
    lead = [r for r in board["firms"] if r["n_lead_matched"]]
    L += ["", f"Lead time vs the corpus's first mainstream item: {len(lead)} firms have "
          f"at least one matched claim (the corpus starts 2026-09-11); the rest are null, "
          f"not zero. Per-firm values are in the JSON receipt.", ""]
    return "\n".join(L) + "\n"
