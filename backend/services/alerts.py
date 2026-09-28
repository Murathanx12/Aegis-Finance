"""Alerts to the owner's phone -- INFO level only, frozen before sent (LANE A).

THE OWNER'S WORDS (2026-09-28)
==============================
    "i want openclaw to send me a message whenever we find something good or a
     good news about a stock, a signal, we can also then analyze it."

The transport already existed (`telegram_bridge`: own bot identity, owner-only
allowlist, redaction at the one choke point). What was missing was a CALLER
and a discipline. This module is the smallest version of both.

WHAT THIS VERSION DOES, AND REFUSES
===================================
* **INFO only.** An alert is RENDERED BY A TEMPLATE from fields already on disk
  (`alerts_sources`). No LLM decides, scores or writes anything here, so the
  spend is $0.00 by construction. `THESIS_CHANGE`, `SIGNAL_CANDIDATE` and
  `PAPER_ACTION` are declared and REFUSED BY NAME (`require_level`) until
  >= ALERT_MIN_GRADED_DATES alert dates are graded.
* **Frozen before sent.** Each alert is ONE ledger row appended (file-locked
  AND fsynced, `disk_guard.locked_append_line(fsync=True)`) BEFORE any send is
  attempted. A row is never edited: a send result is a SECOND row that
  references the first. A crash between the two leaves a frozen row with no
  result -- visible -- rather than a message with no record.
* **What the owner read is frozen too** (review 2026-09-28 F2). The SEND_RESULT
  row carries the exact text, its sha256, `render_version` and the typing-rule
  version(s). `render(row, at=<the send row's created_utc>)` reproduces it byte
  for byte (pinned by test). Rows written before render/2 carry no text; the
  pass receipt says so (`LEDGER_NOTE`).
* **Dedup.** Five rewrites of one fact are one alert. Cluster key =
  (ticker, event type id, normalised fact key); an event joins the cluster whose
  FIRST publication (`observed_utc`) is within ALERT_DEDUP_WINDOW_H of its own.
  The first publication wins and is the alert; each later one is a FOLLOWUP row
  carrying the cluster's running count, and is never sent. The same source URL
  seen again (a collector re-read) has the same content-hash id and writes
  nothing at all.
* **Caps and quiet hours**, in the owner's zone (Asia/Hong_Kong), COMPUTED from
  UTC with zoneinfo -- never from the machine's local clock. A daily cap and a
  per-ticker cap count alerts sent OR that would have been (DRY_RUN,
  HELD_NOT_ENABLED), so a held run reports exactly what a live one would send.
  The cap goes to the MOST IMPORTANT alerts (`rank_key`: declared event-type
  priority, then newest, then the larger known move), and every capped or held
  alert is named in ONE line of the next message that is sent (F4).
  Inside quiet hours nothing is delivered; the first pass after they end
  delivers what was held as ONE digest.
* **Too old is not an alert** (F3). An event public longer than
  ALERT_SEND_MAX_AGE_H before delivery is closed TOO_OLD and counted.
* **Sending is OFF** unless `ALERTS_SEND_ENABLED`. Off, the sender is never
  called and each alert is closed HELD_NOT_ENABLED.
* **Grading hook.** `alert_units` turns frozen rows into `source_scorecard`
  units (entry at the OPEN of the first session that opens AFTER created_utc;
  1/5/21 sessions; vs SPY and the matched size x vol x momentum cell). The date
  count is DISTINCT ENTRY SESSIONS (F10), not UTC calendar dates.
* **Kill rule** (`kill_rule`): once >= ALERT_MIN_GRADED_DATES entry sessions are
  graded at ALERT_KILL_HORIZON sessions, the stream stays live only if
  `source_scorecard.cell_stats` calls the directional alerts ALPHA_DETECTED
  against their matched control. BETA_EXPLAINS / CANNOT_DISTINGUISH switch the
  pass to ONE daily digest, and the digest says why. TOO_FEW is UNDECIDED (no
  power is not no effect) and changes nothing.
* **One pass at a time.** `run_pass` holds `alerts/alert_pass.lock`; a second
  pass refuses by name. A refused or crashed pass still writes a receipt
  (`write_failure_receipt`), because the task runs windowless.

X, Reddit and StockTwits never originate an alert and never generate an order.
Nothing in this module can place an order.

OWED (another builder's file): the one-line registration of
`p_alert_receipts` in `system_health.PROBES`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from backend import config as _cfg
from backend.services import disk_guard as DG

SCHEMA = "alerts/1"
LICENCE = "PRODUCT_EXPERIMENT"

#: The message template. render/1 = the 06:04Z dry-run template (headline cut
#: at 90 characters); render/2 = plain-words fact first, event age, price
#: reaction relative to the event time, one-line summary of unsent alerts.
RENDER_VERSION = "render/2"
#: Printed on every pass receipt: rows written before render/2 carry no text.
LEDGER_NOTE = ("SEND_RESULT rows created before render/2 (2026-09-28, lane A review fix) "
               "carry no rendered text and no text_sha256; FROZEN rows before it carry no "
               "typing_rule_version (they were typed by 8k_item_priority/1 or /2 -- not "
               "recorded). Those rows are never edited.")

#: Declared levels. Only LIVE_LEVELS may be frozen in this version.
LEVELS: tuple[str, ...] = ("INFO", "THESIS_CHANGE", "SIGNAL_CANDIDATE", "PAPER_ACTION")
LIVE_LEVELS: tuple[str, ...] = ("INFO",)

#: Which source kinds may ORIGINATE an alert. Everything else may at most confirm.
ORIGINATING_KINDS: tuple[str, ...] = ("sec_8k", "sec_form4")
SOCIAL_KINDS: tuple[str, ...] = ("x", "twitter", "reddit", "stocktwits")

#: Send modes.
MODE_LIVE, MODE_DRY, MODE_HELD = "LIVE", "DRY_RUN", "HELD_NOT_ENABLED"
#: Result statuses that close an alert (no later pass touches it again).
DELIVERED = ("SENT", "DRY_RUN", "HELD_NOT_ENABLED")
CAPPED = ("CAPPED_DAILY", "CAPPED_TICKER")
TERMINAL = DELIVERED + CAPPED + ("GAVE_UP", "REFUSED_LEVEL", "TOO_OLD")
#: Closed without reaching the owner: named in the next sent message's summary.
UNSENT = CAPPED + ("HELD_NOT_ENABLED", "TOO_OLD")


class AlertRefused(RuntimeError):
    """The alert pass will not act on this input. Named, never a silent no-op."""


class AlertLevelRefused(AlertRefused):
    """A level above INFO was asked for before the grading gate was met."""


# ───────────────────────────────── paths ────────────────────────────────────

def default_root() -> Path:
    return Path(_cfg.OPTIMUS_LEDGER_DIR) / "alerts"


def ledger_path(root: Optional[Path] = None) -> Path:
    return Path(root or default_root()) / "alerts.jsonl"


def stop_file(root: Optional[Path] = None) -> Path:
    return Path(root or default_root()) / "STOP"


def lock_path(root: Optional[Path] = None) -> Path:
    return Path(root or default_root()) / "alert_pass.lock"


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(s: Any) -> datetime:
    t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _parse_or_none(s: Any) -> Optional[datetime]:
    try:
        return _parse(s) if s else None
    except (TypeError, ValueError):
        return None


def _h(*parts: Any, n: int = 12) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:n]


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─────────────────────────────── the levels ─────────────────────────────────

def require_level(level: str, n_graded_dates: int) -> str:
    """INFO passes. Every other level is refused by name with the gate's count."""
    if level not in LEVELS:
        raise AlertLevelRefused(f"REFUSED: unknown alert level {level!r}; declared: {LEVELS}")
    if level in LIVE_LEVELS:
        return level
    need = int(_cfg.ALERT_MIN_GRADED_DATES)
    raise AlertLevelRefused(
        f"REFUSED: level {level} needs >= {need} graded alert dates; have {int(n_graded_dates)}"
        + ("" if n_graded_dates < need else " (and is not built in this version)"))


def assert_can_originate(event: dict) -> None:
    kind = str(event.get("source_kind") or "")
    if not kind:
        raise AlertRefused("REFUSED: event has no source_kind; an untraceable event cannot alert")
    if kind in ORIGINATING_KINDS and event.get("lane") == "truth" and event.get("source_url"):
        return
    lane = "social" if kind.lower() in SOCIAL_KINDS else (event.get("lane") or "discovery")
    raise AlertRefused(f"REFUSED: source {kind!r} ({lane} lane"
                       + ("" if event.get("source_url") else ", no primary-source link")
                       + ") may confirm an alert, never originate one")


# ─────────────────────────────── the ledger ─────────────────────────────────

def read_ledger(root: Optional[Path] = None) -> list[dict]:
    p = ledger_path(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def append_row(row: dict, root: Optional[Path] = None) -> dict:
    """Append one row, flushed AND fsynced, under the ledger's file lock."""
    DG.locked_append_line(ledger_path(root), json.dumps(row, default=str, sort_keys=True),
                          fsync=True)
    return row


def frozen_alerts(rows: Iterable[dict]) -> list[dict]:
    return [r for r in rows if r.get("kind") == "FROZEN"]


def send_state(rows: Iterable[dict]) -> dict[str, dict]:
    """alert id -> {"status": latest result status, "attempts": n failed/sent tries,
    "at": its time}."""
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("kind") != "SEND_RESULT":
            continue
        for aid in r.get("refers_to") or []:
            s = out.setdefault(aid, {"status": None, "attempts": 0, "at": None})
            s["status"], s["at"] = r.get("status"), r.get("created_utc")
            if r.get("status") in ("SENT", "SEND_FAILED"):
                s["attempts"] += 1
    return out


# ──────────────────────────────── identity ──────────────────────────────────

def alert_id(event: dict) -> str:
    """Content hash of one PUBLICATION: re-reading the same URL collides."""
    return "A" + _h(event.get("ticker"), event.get("event_type_id"), event.get("fact_key"),
                    event.get("source_url"))


def cluster_id(ticker: str, event_type_id: str, fact_key: str, first_observed_utc: str) -> str:
    return "C" + _h(ticker, event_type_id, fact_key, first_observed_utc)


def find_cluster(event: dict, rows: Iterable[dict]) -> Optional[dict]:
    """The FROZEN alert whose cluster this event joins, or None (it starts one).

    Rule: same (ticker, event_type_id, fact_key) and |observed - the cluster's
    FIRST observed| <= ALERT_DEDUP_WINDOW_H."""
    win = timedelta(hours=float(_cfg.ALERT_DEDUP_WINDOW_H))
    o = _parse(event["observed_utc"])
    best = None
    for r in frozen_alerts(rows):
        if (r.get("ticker"), r.get("event_type_id"), r.get("fact_key")) != \
                (event.get("ticker"), event.get("event_type_id"), event.get("fact_key")):
            continue
        if abs(o - _parse(r["observed_utc"])) <= win:
            if best is None or _parse(r["observed_utc"]) < _parse(best["observed_utc"]):
                best = r
    return best


# ───────────────────────────── the frozen fields ────────────────────────────

def contradictions(event: dict, price: dict, peers: Iterable[dict]) -> str:
    """What contradicts the event, or "none found (checked: ...)". Never blank."""
    found = []
    prior = event.get("direction_prior")
    after = price.get("move_basis") != "BEFORE_EVENT"
    if prior in (1, -1) and price.get("price_state") == "PRICED" and after:
        z5 = float(price.get("move_5s_sigma") or 0.0)
        if prior * z5 <= -1.0:
            found.append(f"the price moved {z5:+.1f} sigma over 5 sessions, against this "
                         f"event type's {'positive' if prior > 0 else 'negative'} direction prior")
    for p in peers:
        pp = p.get("direction_prior")
        if p is event or p.get("ticker") != event.get("ticker") or prior not in (1, -1):
            continue
        if pp in (1, -1) and pp == -prior:
            found.append(f"an opposite-prior SEC event for {p['ticker']} in the window: "
                         f"{p.get('event_type_id')} ({p.get('source_url')})")
    if found:
        return "; ".join(found)
    checked = [f"opposite-prior SEC events for {event.get('ticker')} in the "
               f"last {int(_cfg.ALERT_DEDUP_WINDOW_H)} h"]
    if prior in (1, -1) and after:
        checked.insert(0, "the 5-session price move vs the event type's direction prior")
    elif prior in (1, -1):
        checked.append("no close after the event is on disk, so the price cannot contradict "
                       "it yet")
    else:
        checked.append("the event type carries no direction prior, so a price move cannot "
                       "contradict it")
    return "none found (checked: " + "; ".join(checked) + ")"


def not_known(event: dict, n_graded_dates: int) -> str:
    out = []
    if event.get("source_kind") == "sec_8k":
        out.append("no typed extraction was run (no LLM in this version): the event type "
                   "comes from the 8-K item code alone")
        c = event.get("event_type_candidates") or []
        if len(c) > 1:
            out.append(f"the item maps to {len(c)} event types ({' | '.join(c)}); which one "
                       f"applies is not determined")
        out.append("whether the market saw this before the filing (a press release often "
                   "precedes the 8-K)")
        if event.get("amendment"):
            out.append("this is an amended filing; what it changes is not read")
    if event.get("source_kind") == "sec_form4":
        out.append("whether the purchases are routine or opportunistic is not classified; "
                   "the bulk tape has no acceptance time, so availability is the filing "
                   "date's end of day")
    out.append(f"whether alerts like this carry information: {int(n_graded_dates)} of "
               f"{int(_cfg.ALERT_MIN_GRADED_DATES)} alert dates graded")
    return "; ".join(out)


def build_frozen_row(event: dict, *, now: datetime, price: dict, peers: list[dict],
                     n_graded_dates: int, cluster: str, level: str = "INFO") -> dict:
    from backend.services import alerts_sources as S
    level = require_level(level, n_graded_dates)
    et = S.event_time(event)
    return {
        "schema": SCHEMA, "kind": "FROZEN", "licence": LICENCE,
        "id": alert_id(event), "created_utc": _iso(now), "level": level,
        "ticker": event["ticker"], "company": event.get("company"),
        "event_type_id": event["event_type_id"],
        "event_type_candidates": event.get("event_type_candidates") or [event["event_type_id"]],
        "direction_prior": event.get("direction_prior"),
        "direction_prior_basis": event.get("direction_prior_basis",
                                           "event_vocabulary prior" if event.get(
                                               "direction_prior") is not None else None),
        "fact": event["fact"], "fact_key": event["fact_key"],
        "fact_line": event.get("fact_line") or event["fact"],
        "headline": event.get("headline"), "primary_item": event.get("primary_item"),
        "typing_rule_version": event.get("typing_rule_version") or S.TYPING_RULE_VERSION,
        "render_version": RENDER_VERSION,
        "source_url": event["source_url"], "source_url_kind": event.get("source_url_kind"),
        "source_kind": event["source_kind"], "lane": event["lane"],
        "observed_utc": event["observed_utc"], "published_utc": event.get("published_utc"),
        "event_utc": _iso(et) if et else None,
        "accession": event.get("accession"),
        "confirmations": event.get("confirmations") or {"n": 0, "sources": [], "first_url": None},
        **{k: price.get(k) for k in ("price_state", "last_price", "last_price_ts",
                                     "last_price_basis", "sigma_daily", "move_1s_sigma",
                                     "move_5s_sigma", "already_moved",
                                     "already_moved_threshold_sigma", "move_basis",
                                     "reaction_state", "next_open_utc")},
        "contradicts": contradictions(event, price, peers),
        "not_known": not_known(event, n_graded_dates),
        "cluster_id": cluster, "cluster_count": 1,
        #: never updated: the delivery state is the latest SEND_RESULT (`send_state`)
        "send_status": "PENDING",
        "llm_calls": 0,
    }


# ─────────────────────────────── the message ────────────────────────────────

#: A phone notice, not a report: the frozen row carries the long form. Six
#: lines per alert, plus at most one line naming alerts that were not sent.
MAX_MESSAGE_LINES = 7
FACT_LINE_MAX = 170
ET_TZ = "America/New_York"


def cut_words(text: Any, n: int) -> str:
    """Whitespace-normalised, cut at a WORD boundary to at most `n` characters,
    with "..." when cut. The important words come first in every template, so
    a cut loses the least important ones."""
    t = " ".join(str(text or "").split())
    if len(t) <= n:
        return t
    head = t[: n - 3]
    sp = head.rfind(" ")
    if sp >= n // 2:
        head = head[:sp]
    return head.rstrip(" ,;:(-") + "..."


def age_words(seconds: float) -> str:
    """"40 minutes ago", "17 hours ago", "3 days ago" (plain words, floor)."""
    s = max(0.0, float(seconds))
    if s < 3600:
        n, u = max(1, int(s // 60)), "minute"
    elif s < 48 * 3600:
        n, u = int(s // 3600), "hour"
    else:
        n, u = int(s // 86400), "day"
    return f"{n} {u}{'' if n == 1 else 's'} ago"


def _fmt(t: datetime, tz: str) -> str:
    return t.astimezone(ZoneInfo(tz)).strftime("%a %m-%d %H:%M")


def _row_fact_line(row: dict) -> str:
    """render/2 rows carry `fact_line`; older rows are rebuilt from the item."""
    if row.get("fact_line"):
        return str(row["fact_line"])
    from backend.services import alerts_sources as S
    m = re.match(r"8k_item:(\d+\.\d+)$", str(row.get("fact_key") or ""))
    if m:
        return (f"{row.get('ticker')} {S.plain_item(m.group(1))} (8-K Item {m.group(1)}). "
                f"{str(row.get('company') or '').rstrip('.')}".rstrip() + ".")
    return f"{row.get('ticker')}: {row.get('fact') or ''}"


def _event_utc_of(row: dict) -> Optional[datetime]:
    return (_parse_or_none(row.get("event_utc")) or _parse_or_none(row.get("published_utc"))
            or _parse_or_none(row.get("observed_utc")))


def _z(x: Any) -> str:
    """A sigma move to one decimal, never "-0.0"."""
    v = round(float(x), 1)
    return f"{v if v != 0 else 0.0:+.1f}"


def _price_line(row: dict, at: datetime) -> str:
    owner = str(_cfg.ALERT_OWNER_TZ)
    hk = "HKT" if owner == "Asia/Hong_Kong" else owner
    if row.get("price_state") != "PRICED":
        return "Price: " + cut_words(row.get("price_state") or "UNPRICED: no price field", 120)
    before = (f"{row['last_price']:.2f} at the {row['last_price_ts'][5:10]} close, "
              f"{_z(row['move_1s_sigma'])} sigma 1d, {_z(row['move_5s_sigma'])} sigma 5d")
    if row.get("move_basis") == "BEFORE_EVENT":
        nxt = _parse_or_none(row.get("next_open_utc"))
        if row.get("reaction_state") == "MARKET_NOT_TRADED_SINCE" and nxt is not None:
            verb = "opens" if at < nxt else "opened"
            tail = "" if at < nxt else "; no close after it is on disk yet"
            return (f"Move since filing: UNKNOWN, market has not traded since this filing; "
                    f"next session {verb} {_fmt(nxt, owner)} {hk} "
                    f"({_fmt(nxt, ET_TZ)[-5:]} ET){tail}. Before it: {before}.")
        return (f"Move since filing: UNKNOWN, no close after the filing is on disk. "
                f"Before it: {before}.")
    k = float(row.get("already_moved_threshold_sigma") or 2.0)
    moved = (f"MOVED >= {k:g} sigma already" if row.get("already_moved")
             else f"within {k:g} sigma")
    when = "after the filing" if row.get("move_basis") == "INCLUDES_EVENT" else "event time unknown"
    return f"Price {before} ({when}): {moved}."


def render(row: dict, *, at: Optional[datetime] = None) -> str:
    """At most six lines of plain text for one frozen row:

      1. AEGIS <T> what happened, in plain words (the key noun early; the
         company's legal name last, so a word-boundary cut loses only that)
      2. when it became public (ET and the owner's zone) and its age at `at`
      3. the price, relative to the EVENT time (UNKNOWN when no close after it)
      4. the primary source link
      5. what is not known; what contradicts it
      6. level, id, and how to ask for the long form

    Pure: reads only `row` and `at` (default: the row's `created_utc`). The
    same row, the same `at` and the same RENDER_VERSION give the same bytes,
    which is how a SEND_RESULT's stored text is re-derived. No advice: nothing
    in the template tells anyone to trade."""
    at = (at or _parse(row["created_utc"])).astimezone(timezone.utc)
    owner = str(_cfg.ALERT_OWNER_TZ)
    hk = "HKT" if owner == "Asia/Hong_Kong" else owner
    lines = ["AEGIS " + cut_words(_row_fact_line(row), FACT_LINE_MAX)]
    ev = _event_utc_of(row)
    if ev is not None:
        verb = "Filed" if row.get("source_kind") in ("sec_8k", "sec_form4") else "Public"
        lines.append(f"{verb} {_fmt(ev, ET_TZ)} ET ({_fmt(ev, owner)} {hk}), "
                     f"{age_words((at - ev).total_seconds())}.")
    else:
        lines.append("Filed: time UNKNOWN.")
    lines.append(_price_line(row, at))
    c = row.get("confirmations") or {}
    also = f" (+{c['n']} headline(s))" if c.get("n") else ""
    lines.append(f"Source: {row['source_url']}{also}")
    unk = []
    cands = row.get("event_type_candidates") or []
    if 1 < len(cands) <= 3:
        unk.append("type is one of " + " | ".join(cands))
    elif len(cands) > 3:
        unk.append(f"type is one of {len(cands)} event types (analyze for the list)")
    elif row.get("source_kind") == "sec_8k":
        unk.append("typed from the item code only")
    m = re.search(r"(\d+) of (\d+) alert dates graded", str(row.get("not_known") or ""))
    unk.append(f"{m.group(1)}/{m.group(2)} alert dates graded" if m else "ungraded")
    con = str(row.get("contradicts") or "none found")
    con = "none found" if con.startswith("none found") else con
    lines.append(cut_words("Not known: " + "; ".join(unk) + ". Contradicts: " + con, 220))
    lines.append(f"[{row['level']}] id {row['id']} (reply: analyze {row['id']})")
    return "\n".join(lines[:6])


def render_digest(rows: list[dict], *, header: str, at: Optional[datetime] = None) -> str:
    return "\n\n".join([header] + [render(r, at=at) for r in rows])


def compose(body: str, summary_line: Optional[str]) -> str:
    """The exact text sent: the rendered body, then the unsent-summary line."""
    return body + ("\n" + summary_line if summary_line else "")


def rerender(send_row: dict, rows: Iterable[dict]) -> str:
    """Re-derive a SEND_RESULT's text from the frozen rows it refers to. Equal to
    `send_row["text"]` when the render and typing versions are unchanged."""
    by = {r["id"]: r for r in frozen_alerts(rows)}
    at = _parse(send_row["rendered_at_utc"])
    grp = [by[i] for i in send_row["refers_to"]]
    body = (render_digest(grp, header=send_row["digest_header"], at=at)
            if send_row.get("digest") else render(grp[0], at=at))
    return compose(body, send_row.get("summary_line"))


# ───────────────────────────── the clock ────────────────────────────────────

def _hm(s: str) -> dtime:
    h, m = str(s).split(":")
    return dtime(int(h), int(m))


def owner_local(now: datetime) -> datetime:
    return now.astimezone(ZoneInfo(str(_cfg.ALERT_OWNER_TZ)))


def in_quiet_hours(now: datetime) -> bool:
    t = owner_local(now).time()
    a, b = _hm(_cfg.ALERT_QUIET_START_LOCAL), _hm(_cfg.ALERT_QUIET_END_LOCAL)
    return (a <= t < b) if a <= b else (t >= a or t < b)


def owner_day(t: datetime) -> str:
    return str(owner_local(t).date())


# ─────────────────────────────── grading ────────────────────────────────────

def alert_units(rows: Iterable[dict]) -> list[dict]:
    """FROZEN alert rows -> `source_scorecard.grade_units` units. The unit's
    `ts` is created_utc, so entry is the OPEN of the first session that opens
    after the alert was frozen (before 09:30 ET on a session day: that session)."""
    out = []
    for r in frozen_alerts(rows):
        p = r.get("direction_prior")
        out.append({"unit_id": r["id"], "source": "aegis_alerts",
                    "column": f"{r['level']}:{r['source_kind']}",
                    "claim_type": f"alert_{str(r['level']).lower()}",
                    "ticker": r["ticker"],
                    "direction": {1: "up", -1: "down"}.get(p, "none"),
                    "number_given": False, "horizon_stated": None,
                    "ts": r["created_utc"], "time_basis": "alert_created_utc",
                    "date_only": False, "pit_grade": "frozen_before_sent"})
    return out


def grade_alerts(rows: list[dict], bars: Any = None, *,
                 horizons: Optional[tuple[int, ...]] = None) -> dict:
    """n_alert_dates_graded = distinct ENTRY SESSIONS (the XNYS session whose
    open is the alert's entry) with at least one alert GRADED at
    ALERT_KILL_HORIZON sessions -- a Saturday, a Sunday and a pre-open Monday
    alert share Monday's session and count ONCE (review F10). Plus the kill
    cell (directional alerts only) from `source_scorecard.cell_stats`."""
    horizons = tuple(horizons or _cfg.ALERT_GRADE_HORIZONS)
    kh = int(_cfg.ALERT_KILL_HORIZON)
    need = int(_cfg.ALERT_MIN_GRADED_DATES)
    units = alert_units(rows)
    base = {"n_alerts": len(units), "n_alert_dates_graded": 0, "min_graded_dates": need,
            "distance_to_min": need, "kill_horizon": kh, "kill_cell": None,
            "date_unit": "entry session (XNYS)"}
    if not units:
        return {**base, "state": "NO_ALERTS"}
    if bars is None or not len(bars):
        return {**base, "state": "CANNOT_GRADE: no bars"}
    import pandas as pd
    from backend.services import source_scorecard as SS
    last_bar = pd.Timestamp(pd.to_datetime(bars["date"]).max()).date()
    if not any(_parse(u["ts"]).date() < last_bar for u in units):
        return {**base, "state": f"NO_ELAPSED_HORIZON: every alert is on or after the last bar {last_bar}"}
    try:
        panel = SS.PricePanel(bars)
    except SS.ScorecardRefused as exc:
        return {**base, "state": f"CANNOT_GRADE: {exc}"}
    df = SS.grade_units(units, panel, tuple(sorted(set(horizons) | {kh})))
    df = SS.add_source_drift(df)
    g = df[(df["h"] == kh) & (df["state"] == "GRADED")]
    n = int(g["entry_date"].dropna().nunique()) if len(g) else 0
    states = {int(h): df[df["h"] == h]["state"].value_counts().to_dict() for h in horizons}
    kc = df[(df["h"] == kh) & (df["direction"].isin(["up", "down"]))]
    cell = SS.cell_stats(kc, kh) if len(kc) else {"verdict": "TOO_FEW",
                                                  "why": "no directional alert"}
    return {**base, "state": "GRADED", "n_alert_dates_graded": n,
            "distance_to_min": max(0, need - n), "states_by_h": states,
            "kill_cell": {k: cell.get(k) for k in ("verdict", "n_graded", "n_pub_dates",
                                                   "mean_signed_ctrl", "t_ctrl",
                                                   "t_net_of_source_drift", "loo_month_worst",
                                                   "why")}}


#: Verdicts that, at >= ALERT_MIN_GRADED_DATES, mean "measured and did not beat
#: the control". Anything else (TOO_FEW, a missing cell) is UNDECIDED.
KILL_VERDICTS: tuple[str, ...] = ("BETA_EXPLAINS", "CANNOT_DISTINGUISH")


def kill_rule(grade: dict) -> dict:
    """LIVE, UNDECIDED (stays live), or DIGEST_ONLY once the gate is met and the
    directional alerts were MEASURED and did not beat their matched control.
    TOO_FEW is not a failure: no power is not no effect (review F10)."""
    n = int(grade.get("n_alert_dates_graded") or 0)
    need = int(_cfg.ALERT_MIN_GRADED_DATES)
    if n < need:
        return {"mode": "LIVE", "decision": "NOT_READABLE",
                "why": f"{n} of {need} alert dates graded; the kill rule is not readable yet"}
    cell = grade.get("kill_cell") or {}
    v = cell.get("verdict")
    if v == "ALPHA_DETECTED":
        return {"mode": "LIVE", "decision": "KEEP",
                "why": f"at {n} graded alert dates the directional alerts "
                       f"beat their matched control (t {cell.get('t_ctrl')})"}
    if v not in KILL_VERDICTS:
        return {"mode": "LIVE", "decision": "UNDECIDED",
                "why": (f"UNDECIDED: at {n} graded alert dates the directional-alert cell "
                        f"is {v or 'missing'} ({cell.get('why') or 'no reason given'}); too "
                        f"few is not a failure, so the stream stays as it is")}
    return {"mode": "DIGEST_ONLY", "decision": "KILL",
            "why": (f"Alert stream switched to one daily digest: at {n} graded alert dates, "
                    f"alerts did not beat their matched control at "
                    f"{grade.get('kill_horizon')} sessions (verdict {v}, "
                    f"t {cell.get('t_ctrl')}).")}


# ─────────────────────────────── delivery ───────────────────────────────────

def rank_key(row: dict) -> tuple:
    """The declared, deterministic order in which the daily cap is spent:
    ALERT_EVENT_TYPE_PRIORITY (by fact key; unlisted last), then the NEWER event
    first, then the larger |1-day move in sigma| when it includes the event
    (unknown last), then the id."""
    pri = list(_cfg.ALERT_EVENT_TYPE_PRIORITY)
    fk = row.get("fact_key")
    p = pri.index(fk) if fk in pri else len(pri)
    ev = _event_utc_of(row)
    t = -ev.timestamp() if ev is not None else float("inf")
    mv = row.get("move_1s_sigma")
    known = row.get("move_basis") == "INCLUDES_EVENT" and isinstance(mv, (int, float))
    return (p, t, (0, -abs(float(mv))) if known else (1, 0.0), str(row.get("id")))


def event_age_s(row: dict, now: datetime) -> Optional[float]:
    ev = _event_utc_of(row)
    return (now - ev).total_seconds() if ev is not None else None


def unsent_summary(rows: list[dict], *, now: datetime,
                   exclude: Iterable[str] = ()) -> tuple[Optional[str], list[str]]:
    """ONE line naming every alert closed without reaching the owner (capped,
    held, too old) in the last ALERT_UNSENT_SUMMARY_LOOKBACK_H hours that no SENT
    message has named yet; and those ids. None when there is nothing to name."""
    frozen = {r["id"]: r for r in frozen_alerts(rows)}
    already: set[str] = set()
    for r in rows:
        if r.get("kind") == "SEND_RESULT" and r.get("status") == "SENT":
            already.update(r.get("summarised_ids") or [])
            already.update(r.get("refers_to") or [])
    st = send_state(rows)
    since = now - timedelta(hours=float(_cfg.ALERT_UNSENT_SUMMARY_LOOKBACK_H))
    ex = set(exclude)
    pick = []
    for aid, s in st.items():
        if (aid in frozen and aid not in already and aid not in ex and s["status"] in UNSENT
                and _parse(s["at"]) >= since):
            pick.append((frozen[aid], s["status"]))
    if not pick:
        return None, []
    pick.sort(key=lambda x: rank_key(x[0]))
    why = Counter("over the daily cap" if s == "CAPPED_DAILY" else
                  "over the per-ticker cap" if s == "CAPPED_TICKER" else
                  "too old" if s == "TOO_OLD" else "held while sending was off"
                  for _, s in pick)
    names = []
    for r, _ in pick:
        if r["ticker"] not in names:
            names.append(r["ticker"])
    shown = ", ".join(names[:12]) + (f" +{len(names) - 12} more" if len(names) > 12 else "")
    line = (f"{len(pick)} more filing(s) not sent ("
            + ", ".join(f"{n} {w}" for w, n in why.most_common()) + f"): {shown}; "
            f"reply `report` for the list.")
    return line, [r["id"] for r, _ in pick]


def plan_delivery(rows: list[dict], *, now: datetime, kill: dict) -> dict:
    """Which pending alerts go out now, which are capped, too old, or wait. Pure."""
    st = send_state(rows)
    maxa = int(_cfg.ALERT_MAX_SEND_ATTEMPTS)
    pending = [r for r in frozen_alerts(rows)
               if (st.get(r["id"], {}).get("status") not in TERMINAL)]
    if not pending:
        return {"action": "NOTHING_PENDING", "deliver": [], "capped": [], "gave_up": [],
                "too_old": []}
    gave_up = [r for r in pending if st.get(r["id"], {}).get("attempts", 0) >= maxa]
    pending = [r for r in pending if r not in gave_up]
    max_age = float(_cfg.ALERT_SEND_MAX_AGE_H) * 3600
    too_old = [r for r in pending if (event_age_s(r, now) or 0.0) > max_age]
    pending = [r for r in pending if r not in too_old]
    if in_quiet_hours(now):
        return {"action": "HELD_QUIET_HOURS", "deliver": [], "capped": [],
                "gave_up": gave_up, "too_old": too_old, "held": len(pending)}
    day = owner_day(now)
    used = 0
    by_ticker: Counter = Counter()
    frozen_by_id = {r["id"]: r for r in frozen_alerts(rows)}
    digest_today = False
    for r in rows:
        if r.get("kind") == "SEND_RESULT" and r.get("status") in DELIVERED \
                and owner_day(_parse(r["created_utc"])) == day:
            ids = r.get("refers_to") or []
            used += len(ids)
            by_ticker.update(frozen_by_id[i]["ticker"] for i in ids if i in frozen_by_id)
            digest_today = digest_today or bool(r.get("digest"))
    if kill.get("mode") == "DIGEST_ONLY" and digest_today:
        return {"action": "HELD_DIGEST_ALREADY_TODAY", "deliver": [], "capped": [],
                "gave_up": gave_up, "too_old": too_old, "held": len(pending)}
    deliver, capped = [], []
    used0 = used
    for r in sorted(pending, key=rank_key):
        if used >= int(_cfg.ALERT_DAILY_CAP):
            capped.append((r, "CAPPED_DAILY"))
        elif by_ticker[r["ticker"]] >= int(_cfg.ALERT_PER_TICKER_DAILY_CAP):
            capped.append((r, "CAPPED_TICKER"))
        else:
            deliver.append(r)
            used += 1
            by_ticker[r["ticker"]] += 1
    held_in_quiet = any(in_quiet_hours(_parse(r["created_utc"])) for r in deliver)
    digest = kill.get("mode") == "DIGEST_ONLY" or (len(deliver) >= 2 and held_in_quiet)
    return {"action": "DELIVER", "deliver": deliver, "capped": capped, "gave_up": gave_up,
            "too_old": too_old, "digest": digest, "used_today_before": used0}


def deliver(rows: list[dict], *, now: datetime, mode: str, kill: dict,
            sender: Optional[Callable[[str], Any]], root: Optional[Path] = None) -> dict:
    """Carry out `plan_delivery`. Every outcome is a SEND_RESULT row appended AFTER
    the frozen rows it refers to; a delivered (or would-be) message's row holds
    its exact text, sha256 and versions. The sender is called only in MODE_LIVE."""
    from backend.services import alerts_sources as S
    if mode not in (MODE_LIVE, MODE_DRY, MODE_HELD):
        raise AlertRefused(f"REFUSED: unknown send mode {mode!r}")
    plan = plan_delivery(rows, now=now, kill=kill)
    st = send_state(rows)
    results, messages = [], []

    def result(ids: list[str], status: str, **kw: Any) -> dict:
        row = {"schema": SCHEMA, "kind": "SEND_RESULT", "created_utc": _iso(now),
               "refers_to": ids, "status": status, "mode": mode, **kw}
        append_row(row, root)
        results.append(row)
        rows.append(row)
        return row

    for r in plan.get("gave_up", []):
        result([r["id"]], "GAVE_UP", why=f"{int(_cfg.ALERT_MAX_SEND_ATTEMPTS)} failed attempts")
    for r in plan.get("too_old", []):
        age = event_age_s(r, now) or 0.0
        result([r["id"]], "TOO_OLD", why=(f"public {age / 3600:.1f} h before delivery "
                                          f"(> ALERT_SEND_MAX_AGE_H {_cfg.ALERT_SEND_MAX_AGE_H})"))
    for r, why in plan.get("capped", []):
        result([r["id"]], why)
    batch = plan.get("deliver") or []
    if batch:
        if plan.get("digest"):
            header = (kill["why"] if kill.get("mode") == "DIGEST_ONLY" else
                      f"AEGIS alerts held over quiet hours ({_cfg.ALERT_QUIET_START_LOCAL}-"
                      f"{_cfg.ALERT_QUIET_END_LOCAL} HKT): {len(batch)}")
            groups = [(batch, render_digest(batch, header=header, at=now), True, header)]
        else:
            groups = [([r], render(r, at=now), False, None) for r in batch]
        in_batch = [r["id"] for r in batch]
        for k, (grp, body, is_digest, header) in enumerate(groups):
            ids = [r["id"] for r in grp]
            summary, summarised = (unsent_summary(rows, now=now, exclude=in_batch)
                                   if k == 0 else (None, []))
            text = compose(body, summary)
            messages.append(text)
            kw = {"digest": is_digest, "message_chars": len(text), "text": text,
                  "text_sha256": text_sha256(text), "render_version": RENDER_VERSION,
                  "typing_rule_versions": sorted({str(r.get("typing_rule_version"))
                                                  for r in grp}),
                  "typing_rule_version_now": S.TYPING_RULE_VERSION,
                  "rendered_at_utc": _iso(now), "digest_header": header,
                  "summary_line": summary, "summarised_ids": summarised}
            if mode == MODE_DRY:
                result(ids, "DRY_RUN", **kw)
            elif mode == MODE_HELD:
                result(ids, "HELD_NOT_ENABLED", **kw)
            else:
                if sender is None:
                    raise AlertRefused("REFUSED: LIVE mode with no sender")
                try:
                    sender(text)
                    result(ids, "SENT", **kw)
                except Exception as exc:                           # noqa: BLE001
                    att = max(st.get(i, {}).get("attempts", 0) for i in ids) + 1
                    result(ids, "SEND_FAILED", attempt=att,
                           error=f"{type(exc).__name__}: {str(exc)[:200]}", **kw)
    return {"plan_action": plan["action"], "results": results, "messages": messages,
            "n_delivered_or_would": sum(len(r["refers_to"]) for r in results
                                        if r["status"] in DELIVERED),
            "n_too_old": len(plan.get("too_old") or []),
            "held": plan.get("held", 0)}


def telegram_sender(text: str) -> Any:
    """The existing bridge: owner-only, redacted, plain text."""
    from backend.services import telegram_bridge as TG
    return TG.send(text, markdown=False, tag="alert")


# ─────────────────────────────── the pass ───────────────────────────────────

def resolve_mode(dry_run: bool) -> str:
    if dry_run:
        return MODE_DRY
    return MODE_LIVE if bool(getattr(_cfg, "ALERTS_SEND_ENABLED", False)) else MODE_HELD


def freeze_events(events: list[dict], rows: list[dict], *, now: datetime,
                  prices: dict[str, dict], n_graded_dates: int,
                  root: Optional[Path] = None) -> dict:
    """Append one FROZEN row per new cluster, one FOLLOWUP per later publication.
    Mutates `rows` (the in-memory ledger) as it appends, so a batch dedups
    against itself: the FIRST publication (earliest observed_utc) wins.

    `prices` is keyed by alert id (the price context depends on the EVENT time,
    F3); a ticker key is accepted as a fallback."""
    known = {r.get("id") for r in rows if r.get("kind") in ("FROZEN", "FOLLOWUP")}
    #: one PUBLICATION is one row whatever it was typed as: a re-typing (a new
    #: item-priority rule) must not turn yesterday's filing into a second alert
    seen_pub = {(r.get("ticker"), r.get("source_url")) for r in rows
                if r.get("kind") in ("FROZEN", "FOLLOWUP")}
    counts: Counter = Counter()
    refused: Counter = Counter()
    for e in sorted(events, key=lambda x: (x["observed_utc"], x.get("source_url") or "")):
        try:
            assert_can_originate(e)
        except AlertRefused as exc:
            refused[str(exc)[:80]] += 1
            continue
        aid = alert_id(e)
        if aid in known or (e["ticker"], e["source_url"]) in seen_pub:
            counts["already_in_ledger"] += 1
            continue
        first = find_cluster(e, rows)
        if first is not None:
            n_in = 1 + sum(1 for r in rows if r.get("kind") == "FOLLOWUP"
                           and r.get("cluster_id") == first["cluster_id"])
            row = {"schema": SCHEMA, "kind": "FOLLOWUP", "id": aid, "created_utc": _iso(now),
                   "refers_to": first["id"], "cluster_id": first["cluster_id"],
                   "cluster_count": n_in + 1, "ticker": e["ticker"],
                   "source_url": e["source_url"], "source_kind": e["source_kind"],
                   "observed_utc": e["observed_utc"], "send_status": "NOT_SENT_FOLLOWUP"}
            append_row(row, root)
            rows.append(row)
            known.add(aid)
            seen_pub.add((e["ticker"], e["source_url"]))
            counts["followups"] += 1
            continue
        win = timedelta(hours=float(_cfg.ALERT_DEDUP_WINDOW_H))
        o = _parse(e["observed_utc"])
        peers = [x for x in events if x is not e] + [
            x for x in frozen_alerts(rows) if x.get("ticker") == e["ticker"]
            and abs(o - _parse(x["observed_utc"])) <= win]
        cid = cluster_id(e["ticker"], e["event_type_id"], e["fact_key"], e["observed_utc"])
        price = (prices.get(aid) or prices.get(e["ticker"]) or
                 {"price_state": f"UNPRICED: no price computed for {e['ticker']}"})
        row = build_frozen_row(e, now=now, price=price, peers=peers,
                               n_graded_dates=n_graded_dates, cluster=cid)
        append_row(row, root)                      # FROZEN BEFORE ANY SEND
        rows.append(row)
        known.add(aid)
        seen_pub.add((e["ticker"], e["source_url"]))
        counts["frozen"] += 1
    return {"counts": dict(counts), "refused": dict(refused)}


def run_pass(*, now: Optional[datetime] = None, dry_run: bool = False,
             root: Optional[Path] = None, events: Optional[list[dict]] = None,
             universe: Optional[dict] = None, bars: Any = None,
             sender: Optional[Callable[[str], Any]] = None,
             corpus_root: Optional[Path] = None, insider_frame: Any = None,
             write_receipt: bool = True, lock_timeout_s: float = 5.0) -> dict:
    """One alert pass: lock -> universe -> grade -> events -> freeze -> deliver
    -> receipt. A second concurrent pass REFUSES (`AlertRefused`) by name.

    Every input is injectable (tests pass synthetic events, bars, a fake clock,
    tmp_path and a fake sender); production reads the disk."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    root = Path(root or default_root())
    try:
        with DG.file_lock(lock_path(root), timeout_s=lock_timeout_s):
            return _run_pass_locked(now=now, dry_run=dry_run, root=root, events=events,
                                    universe=universe, bars=bars, sender=sender,
                                    corpus_root=corpus_root, insider_frame=insider_frame,
                                    write_receipt=write_receipt)
    except DG.FileLockTimeout as exc:
        raise AlertRefused(f"REFUSED: another alert pass holds {lock_path(root).name} "
                           f"({exc}); two passes would freeze and send the same alerts")


def _run_pass_locked(*, now: datetime, dry_run: bool, root: Path, events: Optional[list[dict]],
                     universe: Optional[dict], bars: Any,
                     sender: Optional[Callable[[str], Any]], corpus_root: Optional[Path],
                     insider_frame: Any, write_receipt: bool) -> dict:
    from backend.services import alerts_sources as S
    run_id = f"{now:%Y%m%dT%H%M%SZ}_{os.getpid()}"
    receipt: dict[str, Any] = {"schema": "alert_pass/2", "run_id": run_id,
                               "created_utc": _iso(now), "llm_calls": 0,
                               "llm_spend_usd": 0.0, "render_version": RENDER_VERSION,
                               "typing_rule_version": S.TYPING_RULE_VERSION,
                               "ledger_note": LEDGER_NOTE}
    if stop_file(root).exists():
        receipt["state"] = f"STOPPED: {stop_file(root)} exists"
        return _finish(receipt, root, write_receipt)
    mode = resolve_mode(dry_run)
    receipt["mode"] = mode
    receipt["send_enabled_flag"] = bool(getattr(_cfg, "ALERTS_SEND_ENABLED", False))
    uni = universe or S.alert_universe(now=now)
    receipt["universe"] = {k: v for k, v in uni.items() if k != "tickers"}
    rows = read_ledger(root)
    if bars is None:
        bars = S.load_price_bars(now=now)
    grade = grade_alerts(rows, bars)
    receipt["grading"] = grade
    receipt["n_alert_dates_graded"] = grade["n_alert_dates_graded"]
    receipt["distance_to_100"] = grade["distance_to_min"]
    kill = kill_rule(grade)
    receipt["kill_rule"] = kill
    if events is None:
        e8, s8 = S.read_8k_events(now=now, universe=uni["tickers"], root=corpus_root)
        e4, s4 = S.read_form4_clusters(now=now, universe=uni["tickers"], frame=insider_frame)
        events = e8 + e4
        s8["staleness"] = S.source_staleness_8k(s8.get("newest_first_seen_utc"), now)
        receipt["sources"] = {"sec_8k": s8, "sec_form4": s4}
        receipt["discovery"] = S.discovery_confirmations(events, now=now, root=corpus_root)
    receipt["n_events"] = len(events)
    closes = S.closes_by_symbol(bars)
    prices = {alert_id(e): S.price_context(e["ticker"], now, closes.get(e["ticker"]),
                                           event_utc=S.event_time(e)) for e in events}
    fz = freeze_events(events, rows, now=now, prices=prices,
                       n_graded_dates=grade["n_alert_dates_graded"], root=root)
    receipt["freeze"] = fz
    dv = deliver(rows, now=now, mode=mode, kill=kill,
                 sender=sender if sender is not None else telegram_sender, root=root)
    receipt["delivery"] = {"plan_action": dv["plan_action"], "held": dv["held"],
                           "n_delivered_or_would": dv["n_delivered_or_would"],
                           "n_too_old": dv["n_too_old"],
                           "statuses": dict(Counter(r["status"] for r in dv["results"])),
                           "n_messages": len(dv["messages"])}
    receipt["messages"] = dv["messages"]
    st8 = ((receipt.get("sources") or {}).get("sec_8k") or {}).get("staleness") or {}
    receipt["state"] = "OK" if st8.get("state", "OK") == "OK" else \
        f"DEGRADED: 8-K source {st8.get('state')} ({st8.get('why')})"
    return _finish(receipt, root, write_receipt)


def _finish(receipt: dict, root: Path, write: bool) -> dict:
    if write:
        p = Path(root) / "receipts" / f"alert_pass_{receipt['run_id']}.json"
        DG.atomic_write_json(p, receipt)
        receipt["receipt_path"] = str(p)
    return receipt


def write_failure_receipt(reason: str, *, root: Optional[Path] = None,
                          now: Optional[datetime] = None, state: str = "REFUSED") -> dict:
    """A refused or crashed pass still leaves a receipt: the task runs under
    pythonw with no window, so this file and the log are the only evidence."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    receipt = {"schema": "alert_pass/2", "run_id": f"{now:%Y%m%dT%H%M%SZ}_{os.getpid()}",
               "created_utc": _iso(now), "state": f"{state}: {reason}"[:2000],
               "llm_calls": 0, "llm_spend_usd": 0.0, "render_version": RENDER_VERSION}
    try:
        return _finish(receipt, Path(root or default_root()), True)
    except OSError as exc:                                         # e.g. the disk is full
        receipt["receipt_write_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return receipt


# ─────────────────────────── the health probe ───────────────────────────────

_RUN_TS = re.compile(r"alert_pass_(\d{8}T\d{6}Z)_\d+\.json$")


def receipts_health(root: Optional[Path] = None, *, now: Optional[datetime] = None) -> dict:
    """The alert stream's liveness from its OWN receipts (review F9): the newest
    receipt by the run id in its FILE NAME (never mtime), its state, and the 8-K
    source's staleness it recorded. ALIVE / STALE / DEAD / UNKNOWN."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    d = Path(root or default_root()) / "receipts"
    best: Optional[tuple[datetime, Path]] = None
    for p in (d.iterdir() if d.exists() else []):
        m = _RUN_TS.search(p.name)
        if m:
            t = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if best is None or t > best[0]:
                best = (t, p)
    if best is None:
        return {"verdict": "UNKNOWN", "evidence_utc": None, "age_s": None,
                "detail": f"no alert_pass_<run id>.json under {d}"}
    t, p = best
    age = (now - t).total_seconds()
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"verdict": "DEAD", "evidence_utc": _iso(t), "age_s": age,
                "detail": f"newest receipt {p.name} unreadable ({type(exc).__name__})"}
    state = str(r.get("state") or "NO STATE")
    lim = float(_cfg.ALERT_RECEIPT_STALE_MIN) * 60
    st8 = ((r.get("sources") or {}).get("sec_8k") or {}).get("staleness") or {}
    detail = f"newest pass {p.name}: {state[:160]}; {age_words(age)}"
    if st8:
        detail += f"; 8-K source {st8.get('state')} (newest row {st8.get('newest_first_seen_utc')})"
    if age > lim:
        v = "STALE"
    elif state.startswith(("OK", "STOPPED")):
        v = "ALIVE"
    else:
        v = "STALE"
    return {"verdict": v, "evidence_utc": _iso(t), "age_s": age, "detail": detail}


def p_alert_receipts(ctx: Any) -> Any:
    """`system_health` probe (registration owed in system_health.PROBES)."""
    from backend.services.system_health import ProbeResult          # noqa: PLC0415
    h = receipts_health(Path(ctx.optimus_dir) / "alerts", now=ctx.now)
    return ProbeResult(h["verdict"], h["evidence_utc"], h["age_s"], h["detail"],
                       proof="run id in the receipt file name; state + sources.sec_8k.staleness "
                             "from its body; never mtime")


__all__ = ["AlertLevelRefused", "AlertRefused", "DELIVERED", "LEDGER_NOTE", "LEVELS",
           "LIVE_LEVELS", "MODE_DRY", "MODE_HELD", "MODE_LIVE", "ORIGINATING_KINDS",
           "RENDER_VERSION", "TERMINAL", "age_words", "alert_id", "alert_units", "append_row",
           "assert_can_originate", "build_frozen_row", "cluster_id", "compose",
           "contradictions", "cut_words", "deliver", "find_cluster", "freeze_events",
           "grade_alerts", "in_quiet_hours", "kill_rule", "not_known", "owner_day",
           "p_alert_receipts", "plan_delivery", "rank_key", "read_ledger", "receipts_health",
           "render", "render_digest", "require_level", "rerender", "resolve_mode", "run_pass",
           "send_state", "telegram_sender", "text_sha256", "unsent_summary",
           "write_failure_receipt"]
