"""Owner calls: typed, dated, twinned and graded (ROADMAP CH-01).

Two things under one frozen contract.

1. THEMES. A frozen rule reads one UTC day of headlines from a fixed set of
   corpus sources and answers TRIGGER / QUIET / UNKNOWN per theme (AI capex
   stress, Iran escalation, election and policy). A TRIGGER on day D opens one
   forward event: entry at the close of the first XNYS session on or after
   D+1, held `horizon` sessions, events never overlapping. A state is a pure
   function of the corpus day file and this contract. Day files are not
   immutable, so `record_states` pins each forward day once (state plus the
   SHA-256 of every source file) in a hash-chained ledger, and a forward event
   counts at a formal read only when its trigger day was pinned on or before
   its entry date.
2. CALLS. An append-only, hash-chained ledger of dated calls (the owner's, or
   the rule's). A call names an instrument pair, a horizon, a claim and a
   probability, is refused once its window has started, and is graded against
   a base-rate twin frozen into the row at write time.

The thresholds were chosen on 2026-11-11 AFTER reading the corpus from
2026-09-11 to 2026-11-10. So every day before `INCEPTION` is labelled
SEEN_BEFORE_FREEZE and is never forward evidence. A day with fewer than
`MIN_TITLES` deduplicated titles is UNKNOWN, never QUIET: a reader outage is
not a quiet news day.

No LLM call, no network, no order, no book. Licence PRODUCT_EXPERIMENT,
descriptive only: nothing here is a signal and no skill is claimed.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

VERSION = "owner-calls/1"
#: First UTC day whose headlines count as forward evidence. The commit that
#: froze this contract was pushed before this day began.
INCEPTION = "2026-11-12"
SOURCES = ("google_news_rss_en_us", "google_news_rss_en_gb", "wsj_markets", "wsj_business",
           "wsj_tech", "wsj_world", "mw_topstories")
MIN_TITLES = 100
CLAIMS = ("below", "above", "abs_at_least")

_CAPEX = (r"\b(capex|capital (spending|expenditures?)|ai (spending|bubble|spend|debt|bonds?)|"
          r"data[- ]cent(er|re)s? (spending|debt|bonds?|costs?)|spending (spree|forecast|binge)|"
          r"ai[- ]trade)\b")
_IRAN = r"\b(iran|iranian|tehran|hormuz|irgc)\b"
_ESCALATION = (r"\b(strikes?|struck|attacks?|attacked|missiles?|drones?|war|escalat\w*|blockade|"
               r"seiz\w+|retaliat\w*|bomb\w*|tanker|closure|clos(e|es|ed|ing)|troops|invasion|"
               r"killed)\b")
_ELECTION = (r"\b(midterms?|mid-term|election|congress|shutdown|house majority|senate majority|"
             r"impeach\w*)\b")

#: `match` must hit the title; `also` (when set) must hit the same title too.
#: `claim` is the hypothesis about (mean return of `long`) minus (`short`, or 0).
THEMES: dict[str, dict] = {
    "ai_capex": {"trial": "TRIAL-OWNER-CALL-A", "match": _CAPEX, "also": None,
                 "min_hits": 3, "min_share": 0.010, "long": ["QQQ"], "short": "SPY",
                 "horizon": 5, "claim": "below", "threshold": 0.0},
    "iran_escalation": {"trial": "TRIAL-OWNER-CALL-B", "match": _IRAN, "also": _ESCALATION,
                        "min_hits": 6, "min_share": 0.025, "long": ["XOM", "CVX", "COP"],
                        "short": "SPY", "horizon": 5, "claim": "above", "threshold": 0.0},
    "election_policy": {"trial": "TRIAL-OWNER-CALL-C", "match": _ELECTION, "also": None,
                        "min_hits": 9, "min_share": 0.053, "long": ["SPY"], "short": None,
                        "horizon": 5, "claim": "abs_at_least", "threshold": 0.02},
}

#: Dated questions. `probability` in a call is P(the claim is true). The owner
#: may answer until the entry session's real close. `rule_window` (inclusive
#: UTC days, all ended before the entry close) lets the frozen rule answer too.
QUESTIONS: dict[str, dict] = {
    "A-NVDA-CLUSTER": {"theme": "ai_capex", "long": ["QQQ"], "short": "SPY",
                       "entry_date": "2026-11-17", "horizon": 5, "claim": "below",
                       "threshold": 0.0, "rule_window": ["2026-11-12", "2026-11-16"],
                       "text": "QQQ returns less than SPY from the 2026-11-17 close (NVIDIA "
                               "reports after it) over the next 5 sessions"},
    "B-ENERGY-42": {"theme": "iran_escalation", "long": ["XOM", "CVX", "COP"], "short": "SPY",
                    "entry_date": "2026-11-13", "horizon": 42, "claim": "above",
                    "threshold": 0.0, "rule_window": None,
                    "text": "An equal-weight XOM/CVX/COP basket returns more than SPY from the "
                            "2026-11-13 close over the next 42 sessions"},
    "C-MIDTERM-35": {"theme": "election_policy", "long": ["SPY"], "short": None,
                     "entry_date": "2026-11-13", "horizon": 35, "claim": "above",
                     "threshold": 0.0, "rule_window": None,
                     "text": "SPY is higher 35 sessions after the 2026-11-13 close"},
}


class CallRefused(ValueError):
    """A call the ledger will not take. `code` is the machine-readable reason."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


# ───────────────────────────────── contract ─────────────────────────────────

def contract(theme: str) -> dict:
    """Everything that decides a theme's states, events and dated questions."""
    return {"version": VERSION, "inception": INCEPTION, "sources": list(SOURCES),
            "min_titles": MIN_TITLES, "theme": theme, **THEMES[theme],
            "dedup": "lower-cased title, counted once per UTC day across the sources",
            "state": "UNKNOWN below min_titles; TRIGGER when hits >= min_hits and "
                     "hits/titles >= min_share; else QUIET",
            "entry": "close of the first XNYS session on or after D+1; events never overlap",
            "questions": {k: v for k, v in sorted(QUESTIONS.items()) if v["theme"] == theme}}


def contract_sha256(theme: str) -> str:
    blob = json.dumps(contract(theme), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode("ascii")).hexdigest()


def _seal(row: dict) -> str:
    blob = json.dumps({k: v for k, v in row.items() if k != "seal"}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


# ────────────────────────────── headline states ─────────────────────────────

@lru_cache(maxsize=None)
def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I)


def title_hits(theme: str, title: str) -> bool:
    spec = THEMES[theme]
    if not _rx(spec["match"]).search(title):
        return False
    return spec["also"] is None or bool(_rx(spec["also"]).search(title))


def daily_counts(data_root: Path, day: str) -> dict:
    """Deduplicated title count and per-theme hits for one UTC day."""
    seen: set[str] = set()
    present: list[str] = []
    hits = {k: 0 for k in THEMES}
    for src in SOURCES:
        f = Path(data_root) / "news_corpus" / src / f"{day}.jsonl"
        if not f.exists():
            continue
        present.append(src)
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    title = str(json.loads(line).get("title") or "").strip()
                except (ValueError, AttributeError):
                    continue
                if not title or title.lower() in seen:
                    continue
                seen.add(title.lower())
                for k in THEMES:
                    hits[k] += title_hits(k, title)
    return {"day": day, "n_titles": len(seen), "sources_present": present, "hits": hits}


def theme_state(counts: dict, theme: str) -> dict:
    spec, n, h = THEMES[theme], int(counts["n_titles"]), int(counts["hits"][theme])
    share = h / n if n else 0.0
    if n < MIN_TITLES:
        state = "UNKNOWN"
    elif h >= spec["min_hits"] and share >= spec["min_share"]:
        state = "TRIGGER"
    else:
        state = "QUIET"
    return {"day": counts["day"], "state": state, "hits": h, "n_titles": n,
            "share": round(share, 5)}


def day_ended(day: str, now: datetime) -> bool:
    end = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(days=1)
    return now >= end


def _days(first: str, last: str) -> list[str]:
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def first_corpus_day(data_root: Path) -> Optional[str]:
    stems = [f.stem for s in SOURCES
             for f in (Path(data_root) / "news_corpus" / s).glob("20??-??-??.jsonl")]
    return min(stems) if stems else None


def states(data_root: Path, theme: str, first: str, last: str, *, now: datetime) -> list[dict]:
    """One state per calendar day in [first, last] that has ENDED. A day with no
    file is UNKNOWN (zero titles), which is the point of walking the calendar."""
    return [theme_state(daily_counts(data_root, d), theme)
            for d in _days(first, last) if day_ended(d, now)]


# ───────────────────────────── sessions and prices ───────────────────────────

def sessions_from(day: date, n: int) -> list[date]:
    """The first `n` XNYS sessions on or after `day`."""
    from backend.services import market_sessions as MS
    out: list[date] = []
    d = day
    while len(out) < n:
        if MS.is_session(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def event_window(day: str, horizon: int) -> tuple[date, date]:
    """(entry session, exit session) for a state read on UTC day `day`."""
    s = sessions_from(date.fromisoformat(day) + timedelta(days=1), horizon + 1)
    return s[0], s[horizon]


def symbols_of(long: Iterable[str], short: Optional[str]) -> list[str]:
    return sorted(set(long) | ({short} if short else set()))


def load_px(data_root: Path, symbols: Iterable[str], *, deep: bool = False):
    """Closes by date. `deep` reads the 2016+ panel (base rates); otherwise the
    recent panel (grading). One file per read: two files can carry different
    split adjustments, and a ratio must not straddle that seam."""
    from backend.services import one_event as OE
    p = Path(data_root) / ("prices_deep" if deep else "prices_2025_26") / "bars.parquet"
    return OE.load_closes([p] if p.exists() else [], symbols)


def excess(px: Any, long: Iterable[str], short: Optional[str], entry: date,
           exit_: date) -> Optional[float]:
    """Mean simple return of `long` (equal weight, bought once, held) minus the
    return of `short` (0 when None). None when any close is missing."""
    syms = symbols_of(long, short)
    if px is None or getattr(px, "empty", True) or any(s not in px.columns for s in syms):
        return None
    if entry not in px.index or exit_ not in px.index:
        return None
    a, b = px.loc[entry, syms], px.loc[exit_, syms]
    if a.isna().any() or b.isna().any():
        return None
    r = b / a - 1.0
    return float(r[list(long)].mean() - (r[short] if short else 0.0))


def satisfied(x: float, claim: str, threshold: float = 0.0) -> bool:
    if claim == "below":
        return x < threshold
    if claim == "above":
        return x > threshold
    if claim == "abs_at_least":
        return abs(x) >= threshold
    raise ValueError(f"unknown claim {claim!r}")


def base_rate(px: Any, long: Iterable[str], short: Optional[str], horizon: int, claim: str,
              threshold: float = 0.0, *, before: date) -> Optional[dict]:
    """The twin: how often the claim was true on NON-OVERLAPPING `horizon`-session
    blocks that ended strictly before `before`. Blocks are counted, never days."""
    syms = symbols_of(long, short)
    if px is None or getattr(px, "empty", True) or any(s not in px.columns for s in syms):
        return None
    dates = [d for d in px[syms].dropna().index if d < before]
    xs, years = [], []
    for i in range(0, len(dates) - horizon, horizon):
        x = excess(px, long, short, dates[i], dates[i + horizon])
        if x is not None:
            xs.append(x)
            years.append(dates[i].year)
    if len(xs) < 2:
        return None
    n = len(xs)
    mean = sum(xs) / n
    sd = (sum((x - mean) ** 2 for x in xs) / (n - 1)) ** 0.5
    hit = [satisfied(x, claim, threshold) for x in xs]
    by_year = {str(y): round(sum(h for h, yy in zip(hit, years) if yy == y)
                             / years.count(y), 3) for y in sorted(set(years))}
    return {"p": round(sum(hit) / n, 4), "n_blocks": n, "mean": round(mean, 6),
            "sd": round(sd, 6), "by_year": by_year, "first": str(dates[0]),
            "bars_through": str(dates[-1])}


# ───────────────────────────────── theme events ─────────────────────────────

def day_fingerprint(data_root: Path, day: str) -> dict[str, str]:
    """SHA-256 of each source's day file, or ABSENT."""
    out = {}
    for src in SOURCES:
        f = Path(data_root) / "news_corpus" / src / f"{day}.jsonl"
        out[src] = hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else "ABSENT"
    return out


def record_states(out_dir: Path, *, data_root: Path, now: datetime) -> dict:
    """Pin every ended forward day that is not pinned yet: one row per day,
    written once, never revised. `drift_days` are pinned days whose files have
    changed since; `state_changed_days` are those where the change would alter
    a theme's state. The pinned state stands in both cases."""
    from backend.services import disk_guard as DG
    path = Path(out_dir) / "states.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    yesterday = (now.astimezone(timezone.utc).date() - timedelta(days=1)).isoformat()
    new = []
    with DG.file_lock(path.with_name(path.name + ".lock")):
        rows = _jsonl(path)
        have = {r["day"] for r in rows}
        prev = rows[-1]["seal"] if rows else "GENESIS"
        for d in _days(INCEPTION, yesterday):
            if d in have:
                continue
            c = daily_counts(data_root, d)
            row = {"schema": "owner-call-state/1", "day": d,
                   "states": {t: {k: v for k, v in theme_state(c, t).items() if k != "day"}
                              for t in THEMES},
                   "files": day_fingerprint(data_root, d),
                   "contracts": {t: contract_sha256(t) for t in THEMES},
                   "recorded_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
                   "prev": prev}
            row["seal"] = prev = _seal(row)
            DG.locked_append_line(path, json.dumps(row, sort_keys=True), fsync=True)
            new.append(row)
    drift, changed = [], []
    for r in rows + new:
        if day_fingerprint(data_root, r["day"]) == r["files"]:
            continue
        drift.append(r["day"])
        c = daily_counts(data_root, r["day"])
        if any(theme_state(c, t)["state"] != r["states"][t]["state"] for t in THEMES):
            changed.append(r["day"])
    return {"recorded": [r["day"] for r in new], "rows": len(rows) + len(new),
            "drift_days": drift, "state_changed_days": changed, "chain": verify_chain(path)}


def forward_states(data_root: Path, theme: str, last: str, *, now: datetime,
                   ledger: Optional[Path] = None) -> list[dict]:
    """States from INCEPTION to `last`. A pinned day reports its PINNED state
    and when it was pinned; an unpinned day reports the live one."""
    ledger = Path(ledger) if ledger else Path(data_root) / "owner_calls" / "states.jsonl"
    pinned = {r["day"]: r for r in _jsonl(ledger)}
    out = []
    for st in states(data_root, theme, INCEPTION, last, now=now):
        r = pinned.get(st["day"])
        out.append({**st, "pinned_utc": None} if r is None else
                   {"day": st["day"], **r["states"][theme], "pinned_utc": r["recorded_utc"]})
    return out


def theme_events(data_root: Path, theme: str, *, now: datetime, px: Any = None,
                 ledger: Optional[Path] = None) -> dict:
    """Forward events (days from INCEPTION) and, separately, the triggers that
    were seen before the freeze. The two chains never mix: a seen trigger does
    not absorb a forward one, and is never counted. A forward event carries
    `counts_at_read`: true only when its trigger day was pinned on or before
    its entry date."""
    spec = THEMES[theme]
    h = int(spec["horizon"])
    if px is None:
        px = load_px(data_root, symbols_of(spec["long"], spec["short"]))
    last_bar = None if px is None or px.empty else px.index[-1]
    yesterday = (now.astimezone(timezone.utc).date() - timedelta(days=1)).isoformat()
    first = first_corpus_day(data_root)
    day_before = (date.fromisoformat(INCEPTION) - timedelta(days=1)).isoformat()
    chains = {"SEEN_BEFORE_FREEZE": states(data_root, theme, first, day_before, now=now)
              if first and first <= day_before else [],
              "FORWARD": forward_states(data_root, theme, yesterday, now=now, ledger=ledger)
              if INCEPTION <= yesterday else []}
    events, counts = [], {"forward_days": len(chains["FORWARD"])}
    for label, rows in chains.items():
        free_from: Optional[date] = None
        for st in rows:
            key = f"{label.lower()}_{st['state'].lower()}"
            counts[key] = counts.get(key, 0) + 1
            if st["state"] != "TRIGGER":
                continue
            entry, exit_ = event_window(st["day"], h)
            if free_from is not None and entry < free_from:
                counts[f"{label.lower()}_absorbed"] = counts.get(f"{label.lower()}_absorbed", 0) + 1
                continue
            free_from = exit_
            ev = {"theme": theme, "evidence": label, "trigger_day": st["day"],
                  "hits": st["hits"], "n_titles": st["n_titles"], "share": st["share"],
                  "entry_date": str(entry), "exit_date": str(exit_), "horizon_sessions": h}
            if label == "FORWARD":
                pin = st.get("pinned_utc")
                ev["pinned_utc"] = pin
                ev["counts_at_read"] = bool(pin) and pin[:10] <= str(entry)
                if not ev["counts_at_read"]:
                    counts["forward_events_not_counted"] = (
                        counts.get("forward_events_not_counted", 0) + 1)
            if last_bar is None or last_bar < exit_:
                ev["status"] = "PENDING"
            else:
                x = excess(px, spec["long"], spec["short"], entry, exit_)
                if x is None:
                    ev["status"] = "CANNOT_GRADE"
                else:
                    ev.update(status="GRADED", outcome=round(x, 6),
                              claim_true=satisfied(x, spec["claim"], spec["threshold"]))
            events.append(ev)
    return {"theme": theme, "contract_sha256": contract_sha256(theme), "counts": counts,
            "bars_last": None if last_bar is None else str(last_bar), "events": events}


def rule_answer(data_root: Path, question: str, *, now: datetime) -> dict:
    """The frozen rule's answer to a dated question: YES when any day of the
    question's window is TRIGGER, UNKNOWN when it cannot say, else ABSTAIN."""
    q = QUESTIONS[question]
    if not q.get("rule_window"):
        return {"question": question, "answer": "NO_RULE", "days": []}
    first, last = q["rule_window"]
    rows = states(data_root, q["theme"], first, last, now=now)
    if any(r["state"] == "TRIGGER" for r in rows):
        ans = "YES"
    elif len(rows) < len(_days(first, last)) or any(r["state"] == "UNKNOWN" for r in rows):
        ans = "UNKNOWN"
    else:
        ans = "ABSTAIN"
    return {"question": question, "answer": ans, "days": rows}


# ───────────────────────────────── call ledger ──────────────────────────────

def _jsonl(path: Path) -> list[dict]:
    from backend.services import one_event as OE
    return OE._jsonl(Path(path))


def verify_chain(path: Path) -> dict:
    """Each row's seal covers its content and the previous row's seal."""
    prev, rows = "GENESIS", _jsonl(path)
    for i, r in enumerate(rows, 1):
        if r.get("prev") != prev or r.get("seal") != _seal(r):
            return {"rows": len(rows), "ok": False, "broken_at": i}
        prev = r["seal"]
    return {"rows": len(rows), "ok": True, "broken_at": None}


def log_call(out_dir: Path, *, data_root: Path, who: str, probability: Optional[float],
             question: Optional[str] = None, text: str = "", long: Optional[list[str]] = None,
             short: Optional[str] = None, horizon: Optional[int] = None,
             claim: Optional[str] = None, threshold: float = 0.0,
             entry_date: Optional[str] = None, written_at: Optional[datetime] = None) -> dict:
    """Append one call. `probability` is P(the claim is true), or None for a
    direction-only call. Refused: a window that has started, a second answer
    by the same person to the same question, symbols the panel cannot price."""
    from backend.services import disk_guard as DG
    from backend.services import one_event as OE
    written = written_at or OE._wall_clock()
    if question is not None:
        if question not in QUESTIONS:
            raise CallRefused("UNKNOWN_QUESTION", question)
        q = QUESTIONS[question]
        long, short, horizon = list(q["long"]), q["short"], int(q["horizon"])
        claim, threshold, entry_date = q["claim"], float(q["threshold"]), q["entry_date"]
        text = text or q["text"]
    if not who or not long or not horizon or claim not in CLAIMS or not text:
        raise CallRefused("INCOMPLETE", "who, text, long, horizon and a known claim are required")
    if probability is not None and not 0.0 < float(probability) < 1.0:
        raise CallRefused("BAD_PROBABILITY", "must be strictly between 0 and 1")
    if entry_date is not None:
        close = OE.session_close(date.fromisoformat(entry_date))
        if close is None:
            raise CallRefused("NOT_A_SESSION", entry_date)
        if close <= written:
            raise CallRefused("WINDOW_STARTED", f"{entry_date} closed {close.isoformat()}")
    twin = base_rate(load_px(data_root, symbols_of(long, short), deep=True), long, short,
                     int(horizon), claim, threshold, before=written.date())
    if twin is None:
        raise CallRefused("NO_BARS", f"cannot price {symbols_of(long, short)} in the deep panel")
    path = Path(out_dir) / "calls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with DG.file_lock(path.with_name(path.name + ".lock")):
        rows = _jsonl(path)
        if question and any(r.get("who") == who and r.get("question") == question for r in rows):
            raise CallRefused("ALREADY_ANSWERED", f"{who} on {question}: a call is never revised")
        row = {"schema": "owner-call/1", "who": who, "question": question,
               "theme": QUESTIONS[question]["theme"] if question else None, "text": text,
               "long": list(long), "short": short, "horizon_sessions": int(horizon),
               "claim": claim, "threshold": float(threshold),
               "probability": None if probability is None else float(probability),
               "entry_date": entry_date,
               "entry_rule": "the named session's close" if entry_date else
                             "close of the first session whose real XNYS close >= written_utc",
               "written_utc": written.isoformat(timespec="seconds"), "twin": twin,
               "licence": "PRODUCT_EXPERIMENT", "skill_claim": "none",
               "prev": rows[-1]["seal"] if rows else "GENESIS"}
        row["call_id"] = "oc_" + _seal(row)[:16]
        row["seal"] = _seal(row)
        DG.locked_append_line(path, json.dumps(row, sort_keys=True), fsync=True)
    return row


def grade_calls(out_dir: Path, *, data_root: Path, now: datetime) -> dict:
    """Grade every call whose window has closed on the bars on disk. A grade is
    written once per call. PENDING is not a failure; CANNOT_GRADE (the bars
    reach the exit but a close is missing), FROZEN_LATE and SEAL_MISMATCH are."""
    from backend.services import disk_guard as DG
    from backend.services import one_event as OE
    out_dir = Path(out_dir)
    rows = _jsonl(out_dir / "calls.jsonl")
    gpath = out_dir / "grades.jsonl"
    done = {g.get("call_id") for g in _jsonl(gpath)}
    counts = {"graded": 0, "pending": 0, "already": 0, "cannot_grade": 0, "frozen_late": 0,
              "seal_mismatch": 0}
    new = []
    for r in rows:
        if r.get("call_id") in done:
            counts["already"] += 1
            continue
        if r.get("seal") != _seal(r):
            counts["seal_mismatch"] += 1
            continue
        written = OE._utc(r["written_utc"])
        h = int(r["horizon_sessions"])
        if r.get("entry_date"):
            s = sessions_from(date.fromisoformat(r["entry_date"]), h + 1)
        else:
            s = sessions_from(written.date(), h + 2)
            s = s if OE.session_close(s[0]) >= written else s[1:]
        entry, exit_ = s[0], s[h]
        if OE.session_close(entry) <= written:
            counts["frozen_late"] += 1
            continue
        px = load_px(data_root, symbols_of(r["long"], r["short"]))
        if px is None or px.empty or px.index[-1] < exit_:
            counts["pending"] += 1
            continue
        x = excess(px, r["long"], r["short"], entry, exit_)
        if x is None:
            counts["cannot_grade"] += 1
            continue
        yes = satisfied(x, r["claim"], r["threshold"])
        p, tp = r.get("probability"), r["twin"]["p"]
        new.append({"call_id": r["call_id"], "who": r["who"], "question": r.get("question"),
                    "entry_date": str(entry), "exit_date": str(exit_), "outcome": round(x, 6),
                    "claim_true": yes, "probability": p,
                    "brier": None if p is None else round((p - yes) ** 2, 6),
                    "twin_probability": tp, "twin_brier": round((tp - yes) ** 2, 6),
                    "graded_at": now.isoformat(timespec="seconds"),
                    "bars_last": str(px.index[-1])})
        counts["graded"] += 1
    for g in new:
        DG.locked_append_line(gpath, json.dumps(g, sort_keys=True), fsync=True)
    return {"calls": len(rows), "counts": counts, "new_grades": new,
            "chain": verify_chain(out_dir / "calls.jsonl")}


# ─────────────────────────────── trial registry ─────────────────────────────

def ensure_owner_call_trials(db_path: Any = None) -> dict[str, int]:
    """Idempotently register the three descriptive trials. Attended: called by
    `scripts/owner_calls.py register` after the owner signs, never at startup."""
    from backend.services.portfolio_intelligence.trial_registry import ensure_trial_registered
    out = {}
    for theme, spec in THEMES.items():
        notes = {"hypothesis": f"after a {theme} headline TRIGGER the claim "
                               f"'{spec['claim']} {spec['threshold']}' on {spec['long']} minus "
                               f"{spec['short']} over {spec['horizon']} sessions is true more "
                               "often than on unconditional blocks",
                 "purpose": "descriptive owner-call trial, PRODUCT_EXPERIMENT, no claim",
                 "primary_metric": ("share of counted forward events where the claim is true"
                                    if spec["claim"] == "abs_at_least" else
                                    "sign-adjusted mean excess over counted forward events"),
                 "decision_rule": "docs/TRIALS/" + spec["trial"] + "*.md",
                 "inception": INCEPTION, "contract_sha256": contract_sha256(theme)}
        out[theme] = ensure_trial_registered("owner-call-" + theme.replace("_", "-"), notes,
                                             db_path=db_path)
    return out
