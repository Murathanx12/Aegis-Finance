"""CH-66: the FULL text of 8-K Exhibit 99 documents, in a store of its own.

WHY THIS EXISTS
===============
The raw SEC collector (`scripts/news_pull.py`, source `sec_edgar_8k_ex99_body`)
keeps the first `SEC_EXHIBIT_COLLECTOR_CUT_CHARS` characters of each exhibit.
Counted 2026-11-19: 4,761 of 5,275 stored bodies are exactly that long, and an
earnings release prints its guidance table after that point. The exhibit URL is
already in every row, so the missing text is one polite request away.

WHY IT IS BESIDE THE COLLECTOR AND NOT IN IT
============================================
The scheduled collector runs from a custody folder that byte-pins nine files
(`scripts/news_pull.py`, `backend/config.py`, the entity tables, ...). Any byte
change to them in the runtime checkout stops collection. This module therefore
changes nothing the collector reads or writes: it READS the collector's day
files and APPENDS to a separate folder, `<data root>/sec_exhibit_full/`.

THE STORE
=========
`<store>/<yyyy-mm>.jsonl`, the month being the filing's acceptance month, one
row per exhibit, append-only:

    raw_id, accession, cik, ticker, tickers, exhibit, items, url, filed_utc,
    fetched_utc, sha256 (of the bytes received), n_chars, text,
    capped, prefix_matches_stored, stored_chars, run_id

`prefix_matches_stored` says whether the collector's stored body is, byte for
byte, the start of the text fetched now. `content_check` ("ok") says the answer
passed `content_mismatch()` below, which is what decides whether it is stored.

WHAT COUNTS AS THE EXHIBIT (fix round, review S1)
=================================================
A 200 answer is stored only when it passes `content_mismatch()`: a text content
type (when the door reports one), a final URL still under the EDGAR archive
prefix, at least `SEC_EXHIBIT_FULL_MIN_CHARS` characters, and the first
`SEC_EXHIBIT_FULL_PREFIX_CHECK_CHARS` characters of the stored collector body
found in it after entity and whitespace normalisation. Anything else (a
throttle page, a landing page, a different document) is a failure with code
CONTENT_MISMATCH: nothing is stored, the exhibit stays owed, and
`SEC_EXHIBIT_FULL_MISMATCH_WAVE` of them in one run stop it as
REFUSED(SOURCE_SUSPECT).

HONEST EXITS
============
`run()` returns a receipt whose `status` is one of

    OK              rows were fetched, no failure
    NOTHING_OWED    no stored body in scope is cut and unfetched
    PARTIAL         some rows fetched, some requests failed
    FAILED          requests were made and none produced a row
    REFUSED         a named refusal (`code`), e.g. SOURCE_BLOCKED on the first
                    403/429 or SOURCE_SUSPECT on a mismatch wave: the run stops
                    there and never retries

and `exit_code()` maps only the first two to 0.

The HTML cleaner is the collector's (`news_pull._strip_html`), so the stored
text and the prefix check agree with the collector's body. It keeps the text of
`<script>`/`<style>` and of hidden elements (review N3); none of the real
exhibits read so far held any.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional

from backend import config as C

SCHEMA = "sec-exhibit-full/1"
RECEIPT_SCHEMA = "sec-exhibit-full-receipt/1"

OK = "OK"
NOTHING_OWED = "NOTHING_OWED"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
REFUSED = "REFUSED"

CORPUS_MISSING = "CORPUS_MISSING"
SCOPE_MISSING = "SCOPE_MISSING"
SOURCE_BLOCKED = "SOURCE_BLOCKED"
SOURCE_SUSPECT = "SOURCE_SUSPECT"
BAD_ARGUMENT = "BAD_ARGUMENT"
CONTENT_MISMATCH = "CONTENT_MISMATCH"

#: the collector's own source row, whose `min_interval_s` floors our pace
COLLECTOR_SOURCE_ID = "sec_edgar_8k_ex99_body"

_HTTP_STATUS = re.compile(r"\bHTTP (?:Error )?(\d{3})\b")


class SecExhibitFullRefused(RuntimeError):
    """A named refusal of the full-exhibit job. Never an empty success."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# ------------------------------------------------------------------ paths

def default_paths(data_root: Path) -> dict:
    dr = Path(data_root)
    # The funnel snapshot sits beside the data root (`backend/data/`), and a
    # release clone's own copy is not the live one: prefer the file next to the
    # data root that was named, else the configured path.
    beside = dr.parent / Path(C.IC_FUNNEL_PATH).name
    return {
        "corpus": dr / C.SEC_EXHIBIT_BODY_DIRNAME,
        "store": dr / C.SEC_EXHIBIT_FULL_DIRNAME,
        "cik_map": dr / C.SEC_EXHIBIT_CIK_MAP_RELPATH,
        "funnel": beside if beside.is_file() else Path(C.IC_FUNNEL_PATH),
        "event_nodes": dr / C.EVENT_NODES_DIRNAME / "event_nodes.jsonl",
    }


def check_inputs(paths: dict) -> None:
    corpus = Path(paths["corpus"])
    if not corpus.is_dir() or not any(corpus.glob("*.jsonl")):
        raise SecExhibitFullRefused(
            CORPUS_MISSING, f"no collector day files under {corpus}")


# ------------------------------------------------------------------ small parsers

def parse_utc(value: Any) -> Optional[datetime]:
    """An aware UTC datetime, or None. A naive stamp is NOT assumed to be UTC:
    a timestamp whose zone is unknown is unusable for a point-in-time gate."""
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value or "").strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def tag_value(row: dict, prefix: str) -> str:
    for t in row.get("entity_tags") or []:
        if isinstance(t, str) and t.startswith(prefix):
            return t[len(prefix):]
    return ""


def item_codes(row: dict) -> list[str]:
    return [t[4:] for t in row.get("entity_tags") or []
            if isinstance(t, str) and t.startswith("8-K:")]


def load_cik_map(path: Path) -> dict[int, list[str]]:
    """CIK -> tickers from SEC's `company_tickers.json`. Missing file -> {}: the
    caller then matches on the row's own tickers only, and says so."""
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[int, list[str]] = {}
    entries = raw.values() if isinstance(raw, dict) else raw
    for e in entries:
        try:
            cik = int(e["cik_str"])
            sym = str(e["ticker"]).upper().strip()
        except (KeyError, TypeError, ValueError):
            continue
        if sym and sym not in out.setdefault(cik, []):
            out[cik].append(sym)
    return out


def row_tickers(row: dict, cik_map: dict[int, list[str]]) -> list[str]:
    """The row's own tickers plus what its CIK maps to, upper-cased, in order."""
    out = [str(t).upper() for t in row.get("tickers") or [] if str(t).strip()]
    try:
        cik = int(tag_value(row, "cik:"))
    except ValueError:
        cik = None
    for sym in cik_map.get(cik, []) if cik is not None else []:
        if sym not in out:
            out.append(sym)
    return out


# ------------------------------------------------------------------ readers

def iter_jsonl(path: Path, stats: Optional[dict] = None) -> Iterator[dict]:
    """Rows of a JSONL file. An unparsable line (e.g. one a crash cut short) is
    skipped and, when `stats` is given, counted in `stats["corrupt_lines"]`."""
    try:
        with Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    row = None
                if isinstance(row, dict):
                    yield row
                elif stats is not None:
                    stats["corrupt_lines"] = stats.get("corrupt_lines", 0) + 1
    except OSError:
        return


def read_body_rows(corpus: Path, *, since: Optional[datetime] = None) -> list[dict]:
    """The collector's rows. Day files are named by first-seen date, so `since`
    skips only files older than the day before it."""
    rows: list[dict] = []
    floor = (since - timedelta(days=1)).date().isoformat() if since else ""
    for f in sorted(Path(corpus).glob("*.jsonl")):
        if floor and f.stem < floor:
            continue
        rows.extend(iter_jsonl(f))
    return rows


def read_full_store(store: Path, *, with_text: bool = True,
                    months: Optional[set] = None,
                    stats: Optional[dict] = None) -> dict[str, dict]:
    """raw_id -> the LAST row written for it. `months` ({"yyyy-mm", ...})
    limits the read to those month files (the month is the filing's).
    Unparsable lines are skipped and counted in `stats["corrupt_lines"]`."""
    out: dict[str, dict] = {}
    if stats is not None:
        stats.setdefault("corrupt_lines", 0)
    d = Path(store)
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.jsonl")):
        if months is not None and f.stem not in months:
            continue
        for row in iter_jsonl(f, stats):
            rid = str(row.get("raw_id") or "")
            if not rid:
                continue
            if not with_text:
                row = {k: v for k, v in row.items() if k != "text"}
            out[rid] = row
    return out


def is_truncated(body: str) -> bool:
    return len(body or "") == int(C.SEC_EXHIBIT_COLLECTOR_CUT_CHARS)


# ------------------------------------------------------------------ scope

def scope_tickers(paths: dict, now: datetime) -> dict:
    """Funnel candidates plus the primary tickers of open event nodes.

    Returns the set AND the age/size of each source, because a candidate set is
    printed with its age before anything is ranked or fetched for it."""
    out: dict = {"tickers": set(), "priority": set(), "sources": {}}
    funnel = Path(paths["funnel"])
    if funnel.is_file():
        try:
            d = json.loads(funnel.read_text(encoding="utf-8"))
            syms = {str(c.get("ticker") or "").upper() for c in d.get("candidates") or []
                    if isinstance(c, dict)}
            syms.discard("")
            gen = parse_utc(d.get("generated_at"))
            age = round((now - gen).total_seconds() / 86400.0, 2) if gen else None
            out["sources"]["funnel"] = {
                "path": str(funnel), "n": len(syms), "generated_at": d.get("generated_at"),
                "age_days": age, "stale_after_days": _funnel_stale_days(),
                # an undateable snapshot is UNKNOWN, never fresh
                "stale": None if age is None else age > _funnel_stale_days()}
            out["tickers"] |= syms
            out["priority"] |= syms
        except (OSError, ValueError) as e:
            out["sources"]["funnel"] = {"n": 0, "error": f"{type(e).__name__}: {e}"}
    else:
        out["sources"]["funnel"] = {"n": 0, "error": "missing"}

    nodes_path = Path(paths["event_nodes"])
    if nodes_path.is_file():
        horizon = now - timedelta(days=float(C.SEC_EXHIBIT_FULL_OPEN_NODE_DAYS))
        latest: dict[str, dict] = {}
        retired: set = set()
        for r in iter_jsonl(nodes_path):
            kind = r.get("row_kind")
            eid = r.get("event_id")
            if kind == "node" and eid:
                latest[eid] = {"t": r.get("primary_ticker"), "seen": r.get("last_seen_utc")}
                retired.discard(eid)
            elif kind == "retire" and eid:
                retired.add(eid)
        syms = set()
        newest = None
        for eid, n in latest.items():
            seen = parse_utc(n["seen"])
            if eid in retired or seen is None or not n["t"]:
                continue
            newest = seen if newest is None or seen > newest else newest
            if horizon <= seen <= now:
                syms.add(str(n["t"]).upper())
        out["sources"]["event_nodes"] = {
            "n": len(syms), "n_nodes": len(latest),
            "newest_last_seen_utc": _iso(newest) if newest else None,
            "open_window_days": C.SEC_EXHIBIT_FULL_OPEN_NODE_DAYS}
        out["tickers"] |= syms
    else:
        out["sources"]["event_nodes"] = {"n": 0, "error": "missing"}
    return out


def _funnel_stale_days() -> float:
    try:
        from backend.services.investment_committee import FUNNEL_STALE_DAYS
        return float(FUNNEL_STALE_DAYS)
    except Exception:  # noqa: BLE001 - the age is still printed; only the bar is unknown
        return float("nan")


def owed(rows: Iterable[dict], done: Iterable[str], cik_map: dict[int, list[str]],
         tickers: Optional[set], priority: Optional[set] = None) -> tuple[list[dict], dict]:
    """Stored bodies that are cut, carry a fetchable URL and are not yet in the
    full store. `tickers=None` means no restriction. Order: names in `priority`
    (the funnel candidates: 25 names against ~1,250 open event nodes, counted
    2026-11-19) first, then newest filing first within each group."""
    done = set(done)
    counts = {"rows": 0, "truncated": 0, "already_fetched": 0, "no_url": 0,
              "no_timestamp": 0, "out_of_scope": 0, "owed": 0}
    seen: set = set()
    out: list[dict] = []
    for r in rows:
        counts["rows"] += 1
        if not is_truncated(r.get("body") or ""):
            continue
        counts["truncated"] += 1
        rid = str(r.get("raw_id") or "")
        url = str(r.get("url") or "")
        if not rid or not url.startswith(C.SEC_EXHIBIT_FULL_URL_PREFIX):
            counts["no_url"] += 1
            continue
        if rid in done:
            counts["already_fetched"] += 1
            continue
        if rid in seen:
            continue
        filed = parse_utc(r.get("published_utc"))
        if filed is None:
            counts["no_timestamp"] += 1
            continue
        syms = row_tickers(r, cik_map)
        if tickers is not None and not (set(syms) & tickers):
            counts["out_of_scope"] += 1
            continue
        seen.add(rid)
        out.append({"row": r, "raw_id": rid, "url": url, "filed": filed, "tickers": syms})
    prio = priority or set()
    out.sort(key=lambda o: (bool(set(o["tickers"]) & prio), o["filed"], o["raw_id"]),
             reverse=True)
    counts["owed"] = len(out)
    counts["owed_priority"] = sum(1 for o in out if set(o["tickers"]) & prio)
    return out, counts


# ------------------------------------------------------------------ the run

def http_status_of(exc: BaseException) -> Optional[int]:
    code = getattr(exc, "code", None) or getattr(exc, "status", None)
    if isinstance(code, int):
        return code
    m = _HTTP_STATUS.search(str(exc))
    return int(m.group(1)) if m else None


def new_run_id(now: datetime) -> str:
    """Seconds + pid alone collide when one process runs twice in a second (a
    receipt named by it would be overwritten), so a random suffix is added."""
    return (f"sxf_{now.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}_{os.getpid()}_"
            f"{uuid.uuid4().hex[:8]}")


def min_pace_s() -> float:
    """The floor on seconds between requests: the config minimum, raised to the
    collector source's own `min_interval_s` when the registry can be read. Never
    below 1.0, whatever either says."""
    floor = max(1.0, float(C.SEC_EXHIBIT_FULL_MIN_PACE_S))
    try:
        from backend.services import news_registry
        floor = max(floor, float(news_registry.get(COLLECTOR_SOURCE_ID).min_interval_s))
    except Exception:  # noqa: BLE001 - the config floor still holds
        pass
    return floor


def pace_problem(pace: Any) -> str:
    """'' when `pace` is an acceptable pace in seconds, else the reason."""
    try:
        p = float(pace)
    except (TypeError, ValueError):
        return f"pace_s must be a number, got {pace!r}"
    floor = min_pace_s()
    if not math.isfinite(p) or p < floor:
        return f"pace_s must be at least {floor:g} s (the collector's own pacing), got {pace!r}"
    return ""


def _norm(s: str) -> str:
    return " ".join(html.unescape(s or "").split())


def content_mismatch(raw: Any, text: str, stored: str) -> str:
    """'' when a 200 answer is the exhibit the collector stored, else why not.

    Checks, in order: the content type the door reports (`http_proof`, set by
    `news_pull._http_get`; absent from a door that does not report it), the
    final URL after redirects, a minimum length, and the stored body's first
    characters found in the text after entity and whitespace normalisation."""
    proof = getattr(raw, "http_proof", None) or {}
    ctype = str(proof.get("content_type") or "").split(";")[0].strip().lower()
    if ctype and ctype not in tuple(C.SEC_EXHIBIT_FULL_CONTENT_TYPES):
        return f"content type {ctype!r} is not a text document"
    final = str(proof.get("url") or "")
    if final and not final.startswith(C.SEC_EXHIBIT_FULL_URL_PREFIX):
        return f"final url {final[:120]!r} is outside the EDGAR archive"
    need = int(C.SEC_EXHIBIT_FULL_MIN_CHARS)
    if len(text) < need:
        return f"{len(text)} chars, fewer than the {need} an exhibit needs"
    ns = _norm(stored)
    # the collector cut its body at a character count, possibly inside an entity:
    # leave its last few characters out of the comparison
    probe = ns[:min(int(C.SEC_EXHIBIT_FULL_PREFIX_CHECK_CHARS), max(0, len(ns) - 16))]
    if not probe:
        return "no stored collector body to compare with"
    if probe not in _norm(text):
        return (f"the first {len(probe)} chars of the stored body (normalised) are not "
                "in the fetched text: prefix mismatch, a different document")
    return ""


def append_row(path: Path, line: str) -> int:
    """Append one JSONL line so it can never fuse with a crash-cut last line:
    under the file's lock, a file that does not end in a newline gets one first.
    Returns 1 when such a partial last line was terminated, else 0.
    (`disk_guard.locked_append_line` is byte-pinned by the collector, so the
    check lives here; `file_lock` is re-entrant, so the append reuses the lock.)"""
    from backend.services import disk_guard

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    terminated = 0
    with disk_guard.file_lock(path.with_name(path.name + ".lock")):
        if path.is_file() and path.stat().st_size:
            with path.open("rb") as fh:
                fh.seek(-1, os.SEEK_END)
                last = fh.read(1)
            if last != b"\n":
                with path.open("ab") as fh:
                    fh.write(b"\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                terminated = 1
        disk_guard.locked_append_line(path, line, fsync=True)
    return terminated


def exit_code(receipt: dict) -> int:
    status = receipt.get("status")
    if status in (OK, NOTHING_OWED):
        return 0
    return 2 if status == REFUSED else 3


def run(paths: dict, *, http_get: Callable[[str], bytes],
        to_text: Callable[[bytes], str], now: datetime,
        out_dir: Optional[Path] = None, max_docs: Optional[int] = None,
        pace_s: Optional[float] = None, all_tickers: bool = False,
        tickers: Optional[Iterable[str]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        clock: Optional[Callable[[], datetime]] = None,
        user_agent_source: str = "") -> dict:
    """Fetch owed full exhibits, newest first, and write a receipt.

    `http_get` and `to_text` are injected: the script passes the collector's own
    network door and HTML cleaner, a test passes fakes. This function never
    builds a request or a User-Agent itself.
    """
    import time as _time

    from backend.services import disk_guard

    run_id = new_run_id(now)
    store = Path(out_dir) if out_dir else Path(paths["store"])
    max_docs = int(C.SEC_EXHIBIT_FULL_MAX_DOCS if max_docs is None else max_docs)
    pace = float(C.SEC_EXHIBIT_FULL_PACE_S if pace_s is None else pace_s)
    sleep = sleep or _time.sleep
    clock = clock or (lambda: datetime.now(timezone.utc))
    receipt: dict = {
        "schema": RECEIPT_SCHEMA, "run_id": run_id, "started_utc": _iso(now),
        "corpus": str(paths["corpus"]), "store": str(store),
        "max_docs": max_docs, "pace_s": pace, "user_agent_source": user_agent_source,
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "fetched": 0, "requests": 0, "failures": [], "rows": [],
        "content_mismatches": 0, "corrupt_lines": 0, "partial_lines_terminated": 0,
    }

    def finish(status: str, code: str = "", detail: str = "") -> dict:
        receipt.update({"status": status, "code": code, "detail": detail})
        if "counts" in receipt:
            # still owed = owed minus what was STORED (a failed request stays owed)
            receipt["remaining_owed"] = max(
                0, int(receipt["counts"].get("owed", 0)) - receipt["fetched"])
        receipt["exit_code"] = exit_code(receipt)
        rdir = store / "receipts"
        disk_guard.atomic_write_json(rdir / f"sec_exhibit_full_{run_id}.json", receipt)
        receipt["receipt_path"] = str(rdir / f"sec_exhibit_full_{run_id}.json")
        return receipt

    if max_docs < 1:
        return finish(REFUSED, BAD_ARGUMENT, "max_docs must be at least 1")
    bad_pace = pace_problem(pace_s if pace_s is not None else pace)
    if bad_pace:
        return finish(REFUSED, BAD_ARGUMENT, bad_pace)
    try:
        check_inputs(paths)
    except SecExhibitFullRefused as e:
        return finish(REFUSED, e.code, e.detail)

    scope: Optional[set]
    priority: set = set()
    if tickers is not None:
        scope = {str(t).upper() for t in tickers if str(t).strip()}
        receipt["scope"] = {"mode": "explicit", "n": len(scope)}
    elif all_tickers:
        scope = None
        receipt["scope"] = {"mode": "all"}
    else:
        s = scope_tickers(paths, now)
        scope, priority = s["tickers"], s["priority"]
        receipt["scope"] = {"mode": "funnel+open_event_nodes", "n": len(scope),
                            "sources": s["sources"]}
        if not scope:
            return finish(REFUSED, SCOPE_MISSING,
                          "no funnel candidates and no open event nodes; pass "
                          "--all-tickers or --tickers to fetch without them")

    cik_map = load_cik_map(paths["cik_map"])
    receipt["cik_map_entries"] = len(cik_map)
    rows = read_body_rows(Path(paths["corpus"]))
    store_stats: dict = {}
    done = read_full_store(store, with_text=False, stats=store_stats)
    receipt["corrupt_lines"] = store_stats["corrupt_lines"]
    todo, counts = owed(rows, done.keys(), cik_map, scope, priority)
    receipt["counts"] = counts
    if not todo:
        return finish(NOTHING_OWED)

    disk_guard.require_free(float(C.SEC_EXHIBIT_FULL_MIN_FREE_GB),
                            "sec_exhibit_full append", path=store)
    blocked = set(int(s) for s in C.SEC_EXHIBIT_FULL_BLOCK_STATUSES)
    cap = int(C.SEC_EXHIBIT_FULL_MAX_CHARS)
    for i, o in enumerate(todo[:max_docs]):
        if i:
            sleep(pace)
        receipt["requests"] += 1
        try:
            raw = http_get(o["url"])
        except Exception as e:  # noqa: BLE001 - classified below, recorded, never swallowed
            status = http_status_of(e)
            receipt["failures"].append({"raw_id": o["raw_id"], "url": o["url"],
                                        "http_status": status, "error": str(e)[:300]})
            if status in blocked:
                return finish(REFUSED, SOURCE_BLOCKED,
                              f"HTTP {status} on request {receipt['requests']}; stopped, "
                              f"no retry, {receipt['fetched']} row(s) kept")
            continue
        text = (to_text(raw) or "").strip()
        if not text:
            receipt["failures"].append({"raw_id": o["raw_id"], "url": o["url"],
                                        "http_status": None, "error": "empty exhibit text"})
            continue
        stored = (o["row"].get("body") or "")
        why = content_mismatch(raw, text, stored)
        if why:
            # not the exhibit: store nothing, leave it owed, count it
            receipt["content_mismatches"] += 1
            receipt["failures"].append({"raw_id": o["raw_id"], "url": o["url"],
                                        "http_status": None, "code": CONTENT_MISMATCH,
                                        "error": f"{CONTENT_MISMATCH}: {why}"})
            wave = int(C.SEC_EXHIBIT_FULL_MISMATCH_WAVE)
            if receipt["content_mismatches"] >= wave:
                return finish(REFUSED, SOURCE_SUSPECT,
                              f"{receipt['content_mismatches']} answer(s) were not the "
                              f"exhibit (wave bar {wave}); stopped, {receipt['fetched']} "
                              "row(s) kept")
            continue
        fetched_at = clock()
        row = {
            "schema": SCHEMA, "raw_id": o["raw_id"],
            "accession": tag_value(o["row"], "accession:") or o["raw_id"].split(":")[0],
            "cik": tag_value(o["row"], "cik:"),
            "ticker": o["tickers"][0] if o["tickers"] else None,
            "tickers": o["tickers"],
            "exhibit": tag_value(o["row"], "exhibit:"),
            "items": item_codes(o["row"]),
            "url": o["url"], "filed_utc": _iso(o["filed"]),
            "fetched_utc": _iso(fetched_at),
            "sha256": hashlib.sha256(bytes(raw)).hexdigest(),
            "n_chars": len(text), "capped": len(text) > cap, "text": text[:cap],
            "stored_chars": len(stored),
            "prefix_matches_stored": text.startswith(stored) if stored else None,
            "content_check": "ok",
            "run_id": run_id,
        }
        month = o["filed"].strftime("%Y-%m")
        receipt["partial_lines_terminated"] += append_row(
            store / f"{month}.jsonl", json.dumps(row, ensure_ascii=False))
        receipt["fetched"] += 1
        receipt["rows"].append({k: row[k] for k in (
            "raw_id", "ticker", "exhibit", "filed_utc", "n_chars", "capped",
            "prefix_matches_stored", "sha256")})
    if receipt["failures"]:
        return finish(PARTIAL if receipt["fetched"] else FAILED, "",
                      f"{len(receipt['failures'])} request(s) failed")
    return finish(OK)
