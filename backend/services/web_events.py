"""The web-event ledger — what the browser saw, typed, timestamped, and never a trade.

THE SHAPE THAT MATTERS (Murat's guidance, 2026-09-22)
====================================================
    OpenClaw -> web-event ledger -> features -> ranker -> decision engine -> broker

and never

    OpenClaw -> BUY

That is a structural claim, not a style preference. A browser agent that emits
"NVDA looks really bullish" has produced something no later process can grade:
there is no horizon, no source, no timestamp, and no way to ask six weeks later
whether it was right. An agent that emits a typed row with an `observed_at`, a
`source_url` and a `horizon_prior` has produced evidence, and evidence is the
only thing this programme knows how to learn from.

So every row this module accepts carries, or is REFUSED:

    observed_at        when WE saw it (not when it happened)
    evidence_date      when the source says it happened
    source_url         the page, so a human can check
    source_type        which registry entry authorised the visit
    event_type         from a closed vocabulary, not free text
    claim              what the source actually said, quoted or close to it
    retrieved_by       openclaw:<profile>, so a bad profile is traceable
    confidence_source  DIRECT_COMPANY_STATEMENT .. AGGREGATOR .. FORUM_CLAIM

`observed_at` and `evidence_date` are separate fields on purpose. A filing dated
last Tuesday that we only read today is not evidence we had last Tuesday, and
conflating the two is precisely how a backtest learns to trade on information it
did not have. `pit_safe_asof()` exists so a feature builder can ask for rows as
they stood at a moment and get an honest answer.

WHAT IS REFUSED
===============
* A row with a `direction` but no `claim` — a direction with nothing behind it
  is a model's opinion wearing an evidence schema.
* An `event_type` outside `EVENT_TYPES`. Free-text types cannot be counted, and
  a feature you cannot count is a feature you cannot test.
* A row whose `source_url` is not on an allowed domain for its `source_type`.
* A row that names an expected RETURN. The ledger records what was observed; the
  ranker decides what it is worth. A collector that could write an expected
  return would be making the decision the whole pipeline exists to make.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

from backend import config as _cfg

LEDGER_DIR = _cfg.OPTIMUS_LEDGER_DIR / "web_events"

#: A closed vocabulary. Counting requires a closed set; free text does not count.
EVENT_TYPES: frozenset[str] = frozenset({
    # filings and company statements
    "filing_8k", "filing_10q", "filing_10k", "filing_form4", "filing_13d",
    "earnings_release", "guidance_change", "capacity_guidance",
    "product_launch", "contract_win", "customer_announcement",
    "supplier_constraint", "management_language_change",
    # third party
    "analyst_revision", "regulatory_decision", "litigation",
    "index_change", "mna", "offering", "buyback", "dividend_change",
    # attention
    "attention_spike", "forum_disagreement",
    # the honest ones
    "no_event_found", "contradiction",
})

#: How much weight the SOURCE deserves before any model reads it.
CONFIDENCE_SOURCES: tuple[str, ...] = (
    "DIRECT_COMPANY_STATEMENT",   # the company's own filing or IR page
    "REGULATOR",                  # SEC, FDA, FTC
    "MAJOR_WIRE",                 # a primary news wire
    "AGGREGATOR",                 # a site restating someone else
    "FORUM_CLAIM",                # a person on the internet
)

#: source_type -> domains that may carry it. A row whose URL is off-registry is
#: refused: it means the browser wandered, and a wandering browser's evidence
#: cannot be attributed to a source whose reliability we track.
SOURCE_REGISTRY: dict[str, dict] = {
    "sec": {"domains": ("sec.gov",), "login": False,
            "types": ("filing_8k", "filing_10q", "filing_10k", "filing_form4",
                      "filing_13d", "mna", "offering")},
    "company_ir": {"domains": (), "login": False,   # () = any, see `_domain_ok`
                   "types": ("earnings_release", "guidance_change",
                             "capacity_guidance", "product_launch",
                             "contract_win", "customer_announcement",
                             "supplier_constraint", "management_language_change")},
    "reddit": {"domains": ("reddit.com",), "login": False,
               "types": ("attention_spike", "forum_disagreement")},
    "news": {"domains": (), "login": False,
             "types": ("analyst_revision", "regulatory_decision", "litigation",
                       "index_change", "mna", "buyback", "dividend_change")},
    "internal": {"domains": (), "login": False,
                 "types": ("no_event_found", "contradiction")},
}

_TICKER = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")


class WebEventRefused(ValueError):
    """The row is not evidence. Never written, never silently dropped."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _domain_ok(source_type: str, url: str) -> bool:
    spec = SOURCE_REGISTRY.get(source_type)
    if spec is None:
        return False
    doms = spec["domains"]
    if not doms:                       # an open category (company IR, news)
        return url.lower().startswith(("http://", "https://"))
    return any(d in url.lower() for d in doms)


def validate(row: dict) -> dict:
    """Return a normalised row, or REFUSE with the reason."""
    missing = [k for k in ("ticker", "source_type", "source_url", "event_type",
                           "claim", "evidence_date") if not row.get(k)]
    if missing:
        raise WebEventRefused(f"REFUSED: missing required field(s) {missing}")

    et = str(row["event_type"])
    if et not in EVENT_TYPES:
        raise WebEventRefused(
            f"REFUSED: event_type {et!r} is not in the closed vocabulary. "
            f"Free-text types cannot be counted, and a feature you cannot count "
            f"is a feature you cannot test. Known: {sorted(EVENT_TYPES)}")

    st = str(row["source_type"])
    if st not in SOURCE_REGISTRY:
        raise WebEventRefused(f"REFUSED: source_type {st!r} is not in the registry")
    if et not in SOURCE_REGISTRY[st]["types"]:
        raise WebEventRefused(
            f"REFUSED: {st!r} may not carry event_type {et!r}. A forum cannot "
            f"file an 8-K, and a filing is not an attention spike.")
    if not _domain_ok(st, str(row["source_url"])):
        raise WebEventRefused(
            f"REFUSED: {row['source_url']!r} is not an allowed URL for "
            f"source_type {st!r}. An off-registry URL means the browser "
            f"wandered, and wandering evidence cannot be attributed.")

    tick = str(row["ticker"]).upper()
    if tick != "*" and not _TICKER.match(tick):
        raise WebEventRefused(f"REFUSED: {tick!r} is not a ticker")

    if row.get("direction_prior") and not str(row.get("claim", "")).strip():
        raise WebEventRefused(
            "REFUSED: a direction with no claim behind it is a model's opinion "
            "wearing an evidence schema")

    for banned in ("expected_return", "target_price", "rank", "position_size",
                   "action", "buy", "sell"):
        if banned in row:
            raise WebEventRefused(
                f"REFUSED: a web event may not carry {banned!r}. The ledger "
                f"records what was OBSERVED; the ranker decides what it is "
                f"worth. A collector that could write an expected return would "
                f"be making the decision the pipeline exists to make.")

    cs = row.get("confidence_source") or "AGGREGATOR"
    if cs not in CONFIDENCE_SOURCES:
        raise WebEventRefused(
            f"REFUSED: confidence_source {cs!r} unknown; use one of "
            f"{CONFIDENCE_SOURCES}")

    out = {
        "observed_at": row.get("observed_at") or _now(),
        "evidence_date": str(row["evidence_date"])[:10],
        "ticker": tick,
        "entity": row.get("entity") or "",
        "source_type": st,
        "source_url": str(row["source_url"]),
        "event_type": et,
        "claim": str(row["claim"])[:1200],
        "direction_prior": row.get("direction_prior") or None,
        "affected_entities": [str(x).upper() for x in (row.get("affected_entities") or [])],
        "horizon_prior": row.get("horizon_prior") or None,
        "confidence_source": cs,
        "retrieved_by": row.get("retrieved_by") or "openclaw:unknown",
    }
    if out["evidence_date"] > out["observed_at"][:10]:
        raise WebEventRefused(
            f"REFUSED: evidence_date {out['evidence_date']} is AFTER "
            f"observed_at {out['observed_at'][:10]}. A source cannot be dated "
            f"later than the moment we read it.")
    out["event_id"] = hashlib.sha256(
        json.dumps({k: out[k] for k in ("ticker", "event_type", "source_url",
                                        "evidence_date", "claim")},
                   sort_keys=True).encode()).hexdigest()[:16]
    return out


def path_for(day: str | date | None = None) -> Path:
    d = str(day or date.today())[:10]
    return LEDGER_DIR / f"events_{d}.jsonl"


def append(rows: Iterable[dict], *, day: str | date | None = None) -> dict:
    """Validate then write. Refusals are COUNTED and returned, never dropped."""
    ok, refused = [], []
    for r in rows:
        try:
            ok.append(validate(r))
        except WebEventRefused as exc:
            refused.append({"row": {k: r.get(k) for k in ("ticker", "event_type",
                                                          "source_url")},
                            "why": str(exc)[:300]})
    p = path_for(day)
    p.parent.mkdir(parents=True, exist_ok=True)
    seen = {e["event_id"] for e in read(day=day)}
    written = 0
    with p.open("a", encoding="utf-8") as fh:
        for e in ok:
            if e["event_id"] in seen:       # a re-scrape is not a new event
                continue
            fh.write(json.dumps(e) + "\n")
            seen.add(e["event_id"])
            written += 1
    return {"receipt": "web_events.append", "path": str(p),
            "accepted": len(ok), "written": written,
            "duplicates": len(ok) - written,
            "refused": len(refused), "refusals": refused[:10]}


def read(*, day: str | date | None = None) -> list[dict]:
    p = path_for(day)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def read_all(limit_days: int = 60) -> list[dict]:
    files = sorted(LEDGER_DIR.glob("events_*.jsonl"))[-limit_days:]
    out: list[dict] = []
    for f in files:
        out += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out


def pit_safe_asof(asof: str | date, *, limit_days: int = 365) -> list[dict]:
    """Rows AS THEY STOOD at `asof` — filtered on observed_at, not evidence_date.

    This is the function a feature builder must use. Filtering on
    `evidence_date` would admit a filing dated last Tuesday that we did not
    actually read until today, which is how a backtest learns to trade on
    information it never had.
    """
    cut = str(asof)[:10]
    return [e for e in read_all(limit_days) if e["observed_at"][:10] <= cut]


def summary(day: str | date | None = None) -> dict:
    rows = read(day=day)
    by_type: dict[str, int] = {}
    by_conf: dict[str, int] = {}
    for e in rows:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
        by_conf[e["confidence_source"]] = by_conf.get(e["confidence_source"], 0) + 1
    return {"day": str(day or date.today())[:10], "n_events": len(rows),
            "n_tickers": len({e["ticker"] for e in rows}),
            "by_event_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
            "by_confidence_source": by_conf,
            "read_me_first": ("Evidence, not decisions. Nothing here carries an "
                              "expected return, a rank or an action — the ranker "
                              "decides what an observation is worth.")}
