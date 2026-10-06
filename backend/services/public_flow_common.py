"""Shared plumbing for the PUBLIC-FLOW SENSORS (chunk C16, 2026-10-07).

USAspending contract awards (`usaspending_awards`) and Senate LDA lobbying
(`lobbying_lda`) are SENSORS: each row carries its provenance (source, endpoint,
crosswalk match and confidence) and its latency (the event's own date vs the
moment this collector first held it). Neither is a trade signal on its own; the
roadmap (2026-10-06 §2 item 10) puts dollars of contracts and lobbying in the
theory table and never an identity attribute.

What lives here
---------------
* the crosswalk loader + name matcher (one YAML for both sources);
* `Client`: one HTTP path per source with a per-host gap (rate limits are
  honoured with a sleep), a rolling-day cap read from our own request log, the
  `official_sources` response classifier, and REFUSAL on a bot check / access
  denied page / rate limit -- recorded, never worked around;
* append-only jsonl tables keyed on `row_id`, stamping `first_seen_utc`;
* the PIT check (an event date AFTER first_seen is refused, not written);
* receipts named with their run id (never overwritten) and the status rule:
  **zero new rows on a US weekday is DEGRADED, not ok**.
"""
from __future__ import annotations

import json
import re
import statistics
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlencode, urlsplit

from backend import config as _config
from backend.services import disk_guard as DG

UA = "AegisFinance-reader/1.0 (personal research; read-only)"
CONFIDENCE_LEVELS = ("high", "medium", "low")


class PublicFlowRefused(RuntimeError):
    """A public-flow step did not run, and why (the class is the first token)."""


# ───────────────────────────── paths, time ───────────────────────────────────

def root(base: Optional[Path] = None) -> Path:
    return Path(base) if base is not None else Path(_config.PUBLIC_FLOW_DIR)


def table_path(table: str, base: Optional[Path] = None) -> Path:
    if not re.fullmatch(r"[a-z0-9_]+", table or ""):
        raise PublicFlowRefused(f"BAD_TABLE: {table!r}")
    return root(base) / "tables" / f"{table}.jsonl"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_date(s: Any) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def parse_dt(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ───────────────────────────── the crosswalk ─────────────────────────────────

def normalize_name(s: Any) -> str:
    """Upper case, '&' -> AND, punctuation dropped, spaces collapsed."""
    t = str(s or "").upper().replace("&", " AND ")
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def load_crosswalk(path: Optional[Path] = None) -> list[dict]:
    """Every crosswalk entry, validated. REFUSES a missing, empty or malformed
    file: matching against nothing would label every row NOT_MAPPED and look
    like a quiet day."""
    p = Path(path or _config.PUBLIC_FLOW_CROSSWALK)
    try:
        import yaml
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PublicFlowRefused(f"NO_CROSSWALK: {p} does not exist") from exc
    except Exception as exc:  # noqa: BLE001 -- unreadable = refuse, with the reason
        raise PublicFlowRefused(f"CROSSWALK_UNREADABLE: {type(exc).__name__}: {exc}") from exc
    entries = (doc or {}).get("entries") if isinstance(doc, dict) else None
    if not entries:
        raise PublicFlowRefused(f"EMPTY_CROSSWALK: {p} has no entries")
    out = []
    for i, e in enumerate(entries):
        if not isinstance(e, dict) or not e.get("ticker"):
            raise PublicFlowRefused(f"CROSSWALK_ROW_{i}: no ticker")
        conf = str(e.get("confidence") or "").lower()
        if conf not in CONFIDENCE_LEVELS:
            raise PublicFlowRefused(f"CROSSWALK_ROW_{i}: confidence {e.get('confidence')!r} "
                                    f"not in {CONFIDENCE_LEVELS}")
        rp = [normalize_name(x) for x in (e.get("recipient_patterns") or []) if normalize_name(x)]
        lp = [normalize_name(x) for x in (e.get("lda_client_patterns") or []) if normalize_name(x)]
        if not rp and not lp:
            raise PublicFlowRefused(f"CROSSWALK_ROW_{i}: {e['ticker']} has no patterns")
        vf, vt = e.get("valid_from"), e.get("valid_to")
        for k, v in (("valid_from", vf), ("valid_to", vt)):
            if v not in (None, "") and parse_date(v) is None:
                raise PublicFlowRefused(f"CROSSWALK_ROW_{i}: {e['ticker']} {k} {v!r} is not a date")
        out.append({**e, "ticker": str(e["ticker"]).upper(), "confidence": conf,
                    "recipient_patterns": rp, "lda_client_patterns": lp,
                    "valid_from": str(vf)[:10] if vf else None, "valid_to": str(vt)[:10] if vt else None,
                    "uei": [str(u).upper() for u in (e.get("uei") or [])]})
    return out


def entry_valid_on(e: dict, on: Any) -> bool:
    """PURE. An entry maps a name to its ticker only inside [valid_from, valid_to]
    (renames, acquisitions, sales). An undated event is matched to undated
    entries only: dating is what keeps a backfill from handing FY2019 Aerojet
    dollars to LHX."""
    d = parse_date(on)
    if d is None:
        return not e.get("valid_from") and not e.get("valid_to")
    vf, vt = parse_date(e.get("valid_from")), parse_date(e.get("valid_to"))
    return (vf is None or d >= vf) and (vt is None or d <= vt)


#: SAM.gov replaced DUNS with the UEI on 2022-04-04; a UEI match before that date
#: would be a back-filled identifier, so only the name rule applies there.
UEI_ERA_FROM = date(2022, 4, 4)


def match_entity(name: Any, crosswalk: list[dict], field_name: str = "recipient_patterns",
                 uei: Optional[str] = None, on: Any = "ANY") -> dict:
    """PURE. {match_status, ticker, crosswalk_confidence, crosswalk_pattern}.

    A known UEI wins outright (exact identifier). Else the LONGEST pattern that
    equals the normalised name or is a prefix followed by a space; two different
    tickers tied on the longest pattern = AMBIGUOUS, never guessed. `on` = the
    event date; only entries valid on it are considered ("ANY" = ignore dates,
    for tests of the pattern rule alone)."""
    if on != "ANY":
        crosswalk = [e for e in crosswalk if entry_valid_on(e, on)]
    d_on = parse_date(on) if on != "ANY" else None
    if uei and (on == "ANY" or (d_on is not None and d_on >= UEI_ERA_FROM)):
        u = str(uei).upper()
        hits = {e["ticker"]: e for e in crosswalk if u in e.get("uei", [])}
        if len(hits) == 1:
            e = next(iter(hits.values()))
            return {"match_status": "MAPPED", "ticker": e["ticker"],
                    "crosswalk_confidence": e["confidence"], "crosswalk_pattern": f"UEI:{u}"}
    n = normalize_name(name)
    best: list[tuple[int, dict, str]] = []
    for e in crosswalk:
        for pat in e.get(field_name) or []:
            if n == pat or n.startswith(pat + " "):
                best.append((len(pat), e, pat))
    if not best:
        return {"match_status": "NOT_MAPPED", "ticker": None, "crosswalk_confidence": None,
                "crosswalk_pattern": None}
    top = max(b[0] for b in best)
    tops = [b for b in best if b[0] == top]
    tickers = {b[1]["ticker"] for b in tops}
    if len(tickers) > 1:
        return {"match_status": "AMBIGUOUS", "ticker": None, "crosswalk_confidence": None,
                "crosswalk_pattern": "|".join(sorted({b[2] for b in tops}))}
    # same ticker on two rows (e.g. HON high and HON low): the LOWER confidence binds
    order = {c: i for i, c in enumerate(CONFIDENCE_LEVELS)}
    _, e, pat = max(tops, key=lambda b: order[b[1]["confidence"]])
    return {"match_status": "MAPPED", "ticker": e["ticker"],
            "crosswalk_confidence": e["confidence"], "crosswalk_pattern": pat}


# ───────────────────────────── HTTP ──────────────────────────────────────────

@dataclass
class Client:
    """One source's HTTP path. `http` is injectable:
    `(method, url, headers, json_body, timeout) -> (status, bytes, content_type)`."""
    source: str
    min_gap_s: float
    day_cap: int
    base: Optional[Path] = None
    http: Optional[Callable] = None
    sleep_fn: Callable[[float], None] = time.sleep
    now_fn: Callable[[], datetime] = now_utc
    log_requests: bool = True
    _last: Optional[float] = None
    n_requests: int = 0
    _day: Optional[int] = None
    statuses: dict = field(default_factory=dict)

    def _log(self, row: dict) -> None:
        self.n_requests += 1
        self.statuses[str(row.get("class"))] = self.statuses.get(str(row.get("class")), 0) + 1
        if not self.log_requests:
            return
        p = root(self.base) / "requests.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        DG.locked_append_line(p, json.dumps(row))

    def day_count(self) -> int:
        """Requests for this source in the last 24 h, from the log (read once)."""
        if self._day is None:
            cut = self.now_fn() - timedelta(days=1)
            n = 0
            try:
                for ln in (root(self.base) / "requests.jsonl").read_text(
                        encoding="utf-8", errors="replace").splitlines()[-50000:]:
                    if f'"source": "{self.source}"' not in ln:
                        continue
                    try:
                        if datetime.fromisoformat(json.loads(ln)["t"]) > cut:
                            n += 1
                    except (ValueError, KeyError, TypeError):
                        continue
            except OSError:
                pass
            self._day = n
        return self._day + self.n_requests

    def _http(self, method: str, url: str, headers: dict, body: Any, timeout: float):
        if self.http is not None:
            return self.http(method, url, headers, body, timeout)
        import requests
        if method == "POST":
            r = requests.post(url, headers=headers, json=body, timeout=timeout)
        else:
            r = requests.get(url, headers=headers, timeout=timeout)
        return r.status_code, r.content, r.headers.get("content-type", "")

    def request_json(self, method: str, url: str, *, params: Optional[dict] = None,
                     body: Any = None, timeout: float = 60.0) -> Any:
        """One paced request; the parsed JSON or `PublicFlowRefused`."""
        from backend.services import browser_policy as BP
        from backend.services.official_sources import classify_response
        if params:
            url = f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"
        money = BP.url_refusal(url)
        if money:
            raise PublicFlowRefused(money)
        if self.day_count() >= int(self.day_cap):
            raise PublicFlowRefused(f"DAY_CAP: {self.source} spent {self.day_cap} requests in 24 h")
        if self._last is not None:
            w = float(self.min_gap_s) - (time.monotonic() - self._last)
            if w > 0:
                self.sleep_fn(w)                   # the declared rate limit, honoured
        self._last = time.monotonic()
        host = (urlsplit(url).hostname or "").lower()
        hd = {"User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "gzip, deflate"}
        t0 = time.monotonic()
        try:
            st, content, _ctype = self._http(method, url, hd, body, timeout)
        except Exception as exc:  # noqa: BLE001 -- a network error is a class, not a crash
            self._log({"t": iso(self.now_fn()), "source": self.source, "host": host,
                       "url": url[:300], "status": None, "class": f"NETWORK:{type(exc).__name__}"})
            raise PublicFlowRefused(f"NETWORK: {type(exc).__name__}: {str(exc)[:160]}") from exc
        cls = classify_response(int(st), content or b"")
        if int(st) in (401, 403):
            # an edge deny ("Access Denied", AkamaiGHost $(SERVE_403)) is a configured
            # block, not a solvable challenge; named apart so nobody "fixes" headers
            cls = "ACCESS_DENIED"
        self._log({"t": iso(self.now_fn()), "source": self.source, "host": host, "url": url[:300],
                   "status": int(st), "class": cls, "bytes": len(content or b""),
                   "ms": int((time.monotonic() - t0) * 1000)})
        if cls != "OK":
            raise PublicFlowRefused(f"{cls}: {self.source} HTTP {st} at {url[:160]}; "
                                    f"nothing is done to get around it")
        try:
            return json.loads((content or b"").decode("utf-8"))
        except ValueError as exc:
            raise PublicFlowRefused(f"MALFORMED_JSON: {self.source} at {url[:160]}") from exc


# ───────────────────────────── tables ────────────────────────────────────────

def pit_ok(event_date: Any, first_seen: Any) -> bool:
    """PURE. The event's own date may not be after the moment we first held it."""
    ed = parse_date(event_date)
    fs = parse_dt(first_seen)
    if ed is None or fs is None:
        return False
    return ed <= fs.date()


def append_rows(table: str, rows: Iterable[dict], *, event_field: str,
                base: Optional[Path] = None, now: Optional[datetime] = None) -> dict:
    """Append rows whose `row_id` is new; stamp `first_seen_utc` (and `public_utc`
    when the row carries none). A row whose `event_field` is after first_seen is
    REFUSED (counted, not written). Returns {written, duplicate, pit_refused,
    no_row_id, rows} -- `rows` are the rows written, as written."""
    p = table_path(table, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = iso(now or now_utc())
    res: dict = {"written": 0, "duplicate": 0, "pit_refused": 0, "no_row_id": 0, "rows": []}
    with DG.file_lock(p.with_name(p.name + ".lock")):
        have = set()
        try:
            for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.search(r'"row_id":\s*"([^"]+)"', ln)
                if m:
                    have.add(m.group(1))
        except OSError:
            pass
        out = []
        for r in rows:
            rid = str(r.get("row_id") or "")
            if not rid:
                res["no_row_id"] += 1
                continue
            if rid in have:
                res["duplicate"] += 1
                continue
            row = {**r, "first_seen_utc": r.get("first_seen_utc") or stamp}
            if not row.get("public_utc"):
                row["public_utc"] = row["first_seen_utc"]
            if not pit_ok(row.get(event_field), row["first_seen_utc"]):
                res["pit_refused"] += 1
                continue
            have.add(rid)
            res["rows"].append(row)
            out.append(json.dumps(row, default=str, ensure_ascii=False))
        if out:
            with p.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(out) + "\n")
            res["written"] = len(out)
    return res


def content_hash(row: dict, fields: tuple) -> str:
    import hashlib
    return hashlib.sha256(json.dumps([row.get(f) for f in fields], default=str,
                                     sort_keys=True).encode()).hexdigest()[:16]


def append_versioned(table: str, rows: Iterable[dict], *, identity_field: str,
                     content_fields: tuple, event_field: str, base: Optional[Path] = None,
                     now: Optional[datetime] = None) -> dict:
    """Append-only with REVISIONS. The row key is the IDENTITY (never an amount);
    an identity already in the table with the same content is `unchanged`; with
    different content it is a REVISION: a new row `<identity>#v<k>` that
    `supersedes` the previous version (both kept, totals read `latest_versions`).
    An identity seen twice inside ONE call is `in_call_repeats` (an anomaly the
    caller must not call benign). Returns the `append_rows` counts plus those."""
    rows = list(rows)
    prior: dict[str, dict] = {}
    for r in read_table(table, base):
        ident = r.get(identity_field)
        if ident is None:
            continue
        if ident not in prior or int(r.get("version") or 1) >= int(prior[ident].get("version") or 1):
            prior[ident] = r
    seen: set = set()
    out, unchanged, revisions, repeats = [], 0, 0, 0
    for r in rows:
        ident = r.get(identity_field)
        if ident in seen:
            repeats += 1
            continue
        seen.add(ident)
        h = content_hash(r, content_fields)
        p = prior.get(ident)
        if p is None:
            out.append({**r, "row_id": str(ident), "version": 1, "content_hash": h, "supersedes": None})
        elif p.get("content_hash") == h:
            unchanged += 1
        else:
            k = int(p.get("version") or 1) + 1
            out.append({**r, "row_id": f"{ident}#v{k}", "version": k, "content_hash": h,
                        "supersedes": p.get("row_id")})
            revisions += 1
    res = append_rows(table, out, event_field=event_field, base=base, now=now)
    res.update(unchanged=unchanged, revisions=revisions, in_call_repeats=repeats)
    return res


def latest_versions(rows: Iterable[dict], identity_field: str) -> list[dict]:
    """PURE. One row per identity: the highest version (a revision supersedes)."""
    best: dict = {}
    for r in rows:
        k = r.get(identity_field)
        if k is None:
            continue
        if k not in best or int(r.get("version") or 1) > int(best[k].get("version") or 1):
            best[k] = r
    return list(best.values())


def read_table(table: str, base: Optional[Path] = None) -> list[dict]:
    out = []
    try:
        lines = table_path(table, base).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


# ───────────────────────────── receipts ──────────────────────────────────────

def is_us_weekday(t: datetime) -> bool:
    """A US/Eastern weekday that is not a federal holiday (observed): agencies do
    not report on a holiday, so zero new rows there is not DEGRADED."""
    try:
        from zoneinfo import ZoneInfo
        et = t.astimezone(ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001 -- no tz database: a fixed -4 h offset
        et = t.astimezone(timezone(timedelta(hours=-4)))
    if et.weekday() >= 5:
        return False
    try:
        import pandas as pd
        from pandas.tseries.holiday import USFederalHolidayCalendar
        d = pd.Timestamp(et.date())
        return d not in set(USFederalHolidayCalendar().holidays(d - pd.Timedelta(days=1),
                                                                d + pd.Timedelta(days=1)))
    except Exception:  # noqa: BLE001 -- no calendar: treat as a weekday (the strict side)
        return True


def pull_status(rows_added: int, refusals: list, now: datetime, *, quiet_ok: bool = False) -> str:
    """PURE. REFUSED when nothing was read; DEGRADED when zero new rows on a US
    weekday (unless the source is legitimately quiet, e.g. quarterly LDA) or when
    some steps refused; else OK."""
    if refusals and rows_added == 0 and all(r.get("fatal") for r in refusals):
        return "REFUSED"
    if rows_added == 0 and is_us_weekday(now) and not quiet_ok:
        return "DEGRADED"
    if refusals:
        return "DEGRADED"
    return "OK"


BACKFILL_LATENCY = "NOT_MEASURABLE_BACKFILL"
#: a row first seen now whose event date precedes the window this target was
#: already read over: its lag measures our coverage, not the publisher's
BEFORE_COVERAGE_LATENCY = "NOT_MEASURABLE_BEFORE_COVERAGE"


def latency_summary(rows: list[dict], event_field: str) -> dict:
    """Days from the event's own date to `first_seen_utc` (the PIT stamp), over
    rows that were NOT read in a backfill. In a backfill every row carries the
    same first_seen, so the 'lag' is the age of the window, not a latency; those
    rows are counted apart and never enter the distribution."""
    lags = []
    n_backfill = sum(1 for r in rows if r.get("latency") == BACKFILL_LATENCY)
    n_before = sum(1 for r in rows if r.get("latency") == BEFORE_COVERAGE_LATENCY)
    rows = [r for r in rows if r.get("latency") not in (BACKFILL_LATENCY, BEFORE_COVERAGE_LATENCY)]
    if not rows:
        return {"n": 0, "n_backfill_not_measurable": n_backfill,
                **({"n_before_coverage_not_measurable": n_before} if n_before else {})}
    for r in rows:
        ed, fs = parse_date(r.get(event_field)), parse_dt(r.get("first_seen_utc"))
        if ed is not None and fs is not None:
            lags.append((fs.date() - ed).days)
    if not lags:
        return {"n": 0}
    lags.sort()

    def q(p: float) -> float:
        return float(lags[min(len(lags) - 1, int(round(p * (len(lags) - 1))))])
    return {"n": len(lags), "median_days": float(statistics.median(lags)), "p10_days": q(0.10),
            "p90_days": q(0.90), "min_days": float(lags[0]), "max_days": float(lags[-1]),
            "n_backfill_not_measurable": n_backfill, "n_before_coverage_not_measurable": n_before,
            "basis": f"first_seen_utc date minus {event_field} (non-backfill rows only)"}


def write_receipt(source: str, body: dict, base: Optional[Path] = None,
                  now: Optional[datetime] = None) -> Path:
    """`receipts/<source>_<UTC stamp>.json`; an existing name is never overwritten."""
    t = now or now_utc()
    d = root(base) / "receipts"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{source}_{t.strftime('%Y%m%dT%H%M%SZ')}.json"
    k = 1
    while p.exists():
        p = d / f"{source}_{t.strftime('%Y%m%dT%H%M%SZ')}_{k}.json"
        k += 1
    DG.atomic_write_json(p, {"source": source, "written_utc": iso(t), **body})
    return p


def last_receipt(source: str, base: Optional[Path] = None) -> Optional[dict]:
    """The newest receipt of `source`, dated by its OWN stamp (never mtime)."""
    best: Optional[tuple[datetime, dict]] = None
    for p in (root(base) / "receipts").glob(f"{source}_*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        t = parse_dt(doc.get("written_utc"))
        if t is not None and (best is None or t > best[0]):
            best = (t, {**doc, "path": str(p)})
    return best[1] if best else None
