"""Usage receipt -- a privacy-preserving traffic counter for the hosted API.

WHY: the hosted site had no usage measurement at all (council 2, business item 1).

OFF by default. `AEGIS_USAGE_RECEIPT=1` switches it on; with it unset the middleware
adds nothing and the `/api/usage/*` routes answer 404.

WHAT IS COUNTED (in memory, per UTC day)
  * requests per route TEMPLATE (`/api/stock/{ticker}`, never the raw path) per status class
  * a separate top-N ticker table for routes that carry a ticker path parameter
  * page views reported by the beacon `POST /api/usage/pageview` (Vercel serves the pages,
    so the backend would otherwise see API calls only)
  * the number of DISTINCT human visitors per day

WHAT IS NEVER STORED OR LOGGED: an IP address, a user agent, a hash, or the key.
  The visitor identity is HMAC-SHA256(key, ip | user-agent), with a random 32-byte key
  that lives only in this process and is REPLACED at every UTC day boundary. Only the set
  of hashes for the current day is held, and only its SIZE is ever reported or written.
  Hashes cannot be linked across days (new key) or restarts (new random key).

MONITORS AND BOTS are excluded from the human counts and counted separately: health /
  static routes, monitor user agents (curl is what `.github/workflows/prod-monitor.yml`
  sends every 10 minutes, Mon-Fri) and obvious bots. A receipt with only monitor traffic
  shows humans = 0.

WHAT SURVIVES A RESTART: nothing, unless `AEGIS_USAGE_RECEIPT_DIR` names a writable
  directory (a mounted volume on Railway; the container filesystem is ephemeral). Every
  report states `since_process_start`, so a restart is not read as zero traffic.
  Receipt files `usage_<date>.json` keep one segment per process; distinct visitors of
  different segments cannot be de-duplicated (keys are gone), so the file reports the sum
  as an UPPER BOUND.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from backend.config import config

ENV_FLAG = "AEGIS_USAGE_RECEIPT"
ENV_TOKEN = "AEGIS_USAGE_TOKEN"
ENV_DIR = "AEGIS_USAGE_RECEIPT_DIR"
TOKEN_HEADER = "x-usage-token"

HUMAN, MONITOR, BOT = "human", "monitor", "bot"

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-^=]{1,12}$")
_SEGMENT_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
MAX_PAGE_SEGMENTS = 3


def _cfg() -> dict[str, Any]:
    return config["usage_receipt"]


def is_enabled() -> bool:
    return os.environ.get(ENV_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def token_ok(supplied: Optional[str]) -> tuple[bool, str]:
    """(ok, reason). Refuses when the token is unset -- never an open default."""
    expected = os.environ.get(ENV_TOKEN, "")
    if not expected:
        return False, "token_unset"
    if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
        return False, "bad_token"
    return True, "ok"


def client_ip(headers: Any, peer: Optional[str]) -> str:
    """The client address as the Railway proxy presents it.

    Railway appends the real peer to `X-Forwarded-For`, so the RIGHTMOST entry is the one the
    trusted proxy wrote; anything to its left is client-supplied and spoofable. The repo had
    no earlier client-IP derivation (no rate limiter reads one), so this is the only one.
    The value is hashed by the caller and never stored.
    """
    xff = headers.get("x-forwarded-for") if headers is not None else None
    if xff:
        last = xff.split(",")[-1].strip()
        if last:
            return last
    return peer or ""


def classify(path: str, user_agent: str) -> str:
    """human | monitor | bot, from the path and the user agent."""
    cfg = _cfg()
    if any(path == p or path.startswith(p) for p in cfg["health_path_prefixes"]) and path != "/":
        return MONITOR
    ua = (user_agent or "").lower()
    if not ua:
        return BOT
    if any(s in ua for s in cfg["monitor_ua_substrings"]):
        return MONITOR
    if any(s in ua for s in cfg["bot_ua_substrings"]):
        return BOT
    return HUMAN


def status_class(code: int) -> str:
    return f"{int(code) // 100}xx"


def normalize_page(path: str) -> Optional[str]:
    """Validate a beacon page path against the allow-list; return its template or None.

    Allowed: "/" or up to three lowercase `[a-z0-9_-]` segments; a ticker after a configured
    prefix (`/stock/NVDA`) is replaced by `{ticker}`. Query strings, dots, percent escapes
    and anything else are refused.
    """
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 80:
        return None
    if path == "/":
        return "/"
    segs = path.strip("/").split("/")
    if not segs or len(segs) > MAX_PAGE_SEGMENTS:
        return None
    out: list[str] = []
    for i, seg in enumerate(segs):
        if i > 0 and segs[i - 1] in _cfg()["page_ticker_prefixes"] and i == 1:
            if not _TICKER_RE.match(seg):
                return None
            out.append("{ticker}")
        elif _SEGMENT_RE.match(seg):
            out.append(seg)
        else:
            return None
    return "/" + "/".join(out)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _Day:
    """One UTC day of counters. `visitors` and `key` exist only for the live day."""

    def __init__(self, date: str) -> None:
        self.date = date
        self.requests: dict[str, dict[str, int]] = {}
        self.tickers: dict[str, int] = {}
        self.pages: dict[str, int] = {}
        self.monitor_requests = 0
        self.bot_requests = 0
        self.human_requests = 0
        self.visitors: Optional[set[bytes]] = set()
        self.key: Optional[bytes] = secrets.token_bytes(32)
        self.capped = False
        self.visitor_count = 0
        self.truncated: dict[str, int] = {"routes": 0, "tickers": 0, "pages": 0}

    def finalize(self) -> None:
        """Keep only the size; drop the hashes and the key for good."""
        self.visitor_count = len(self.visitors or ())
        self.visitors = None
        self.key = None

    def to_dict(self, live: bool) -> dict[str, Any]:
        cfg = _cfg()
        n = len(self.visitors) if live and self.visitors is not None else self.visitor_count
        cap = cfg["visitor_cap"]
        top = sorted(self.tickers.items(), key=lambda kv: (-kv[1], kv[0]))[: cfg["ticker_top_n"]]
        return {
            "date": self.date,
            "human_requests": self.human_requests,
            "monitor_requests": self.monitor_requests,
            "bot_requests": self.bot_requests,
            "distinct_human_visitors": f">={cap}" if self.capped else n,
            "distinct_human_visitors_capped": self.capped,
            "routes": {k: dict(sorted(v.items())) for k, v in sorted(self.requests.items())},
            "tickers_top": [{"ticker": t, "requests": c} for t, c in top],
            "pageviews": dict(sorted(self.pages.items())),
            "dropped_new_keys_over_cap": dict(self.truncated),
        }


class UsageRecorder:
    def __init__(self, clock: Callable[[], datetime] = _utc_now,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._mono = monotonic
        self._lock = threading.Lock()
        started = clock()
        self.process_started_at = started.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.process_id = uuid.uuid4().hex[:12]  # random, identifies a process segment only
        self._today = _Day(started.strftime("%Y-%m-%d"))
        self._history: list[dict[str, Any]] = []
        self._last_flush = 0.0
        self._beacon_visitor: dict[bytes, list[float]] = {}
        self._beacon_global: list[float] = []

    # -- internals (lock held) ------------------------------------------------
    def _roll(self) -> None:
        date = self._clock().strftime("%Y-%m-%d")
        if date != self._today.date:
            old = self._today
            old.finalize()
            self._history.append(old.to_dict(live=False))
            self._history = self._history[-_cfg()["days_kept"]:]
            self._today = _Day(date)
            self._beacon_visitor.clear()
            self._write_receipt(old, force=True)

    def _hash(self, ip: str, ua: str) -> bytes:
        return hmac.new(self._today.key or b"", f"{ip}|{ua}".encode(), hashlib.sha256).digest()

    def _add_visitor(self, ip: str, ua: str) -> bytes:
        h = self._hash(ip, ua)
        vs = self._today.visitors
        if vs is not None and h not in vs:
            if len(vs) >= _cfg()["visitor_cap"]:
                self._today.capped = True
            else:
                vs.add(h)
        return h

    # -- public ---------------------------------------------------------------
    def record_request(self, *, route: Optional[str], path_params: dict[str, Any],
                       status: int, ip: str, user_agent: str, raw_path: str) -> str:
        """Count one request. Returns its class. `route` is the matched template or None."""
        cfg = _cfg()
        kind = classify(raw_path, user_agent)
        with self._lock:
            self._roll()
            day = self._today
            if kind == MONITOR:
                day.monitor_requests += 1
            elif kind == BOT:
                day.bot_requests += 1
            else:
                day.human_requests += 1
                self._add_visitor(ip, user_agent)
                tmpl = route or "unmatched"
                if tmpl not in day.requests and len(day.requests) >= cfg["route_max_tracked"]:
                    day.truncated["routes"] += 1
                    tmpl = "other"
                row = day.requests.setdefault(tmpl, {})
                sc = status_class(status)
                row[sc] = row.get(sc, 0) + 1
                for name in cfg["ticker_param_names"]:
                    t = path_params.get(name)
                    if isinstance(t, str) and _TICKER_RE.match(t):
                        t = t.upper()
                        if t in day.tickers or len(day.tickers) < cfg["ticker_max_tracked"]:
                            day.tickers[t] = day.tickers.get(t, 0) + 1
                        else:
                            day.truncated["tickers"] += 1
                        break
            self._maybe_flush()
        return kind

    def record_pageview(self, template: str, ip: str, user_agent: str) -> str:
        """Count a beacon page view. Returns accepted | rate_limited | bot."""
        cfg = _cfg()
        kind = classify("/api/usage/pageview", user_agent)
        with self._lock:
            self._roll()
            if kind != HUMAN:
                self._today.bot_requests += 1
                return "bot"
            now = self._mono()
            self._beacon_global = [t for t in self._beacon_global if now - t < 60]
            if len(self._beacon_global) >= cfg["beacon_global_per_min"]:
                return "rate_limited"
            h = self._hash(ip, user_agent)
            hits = [t for t in self._beacon_visitor.get(h, []) if now - t < 60]
            if len(hits) >= cfg["beacon_per_visitor_per_min"]:
                self._beacon_visitor[h] = hits
                return "rate_limited"
            if len(self._beacon_visitor) > cfg["visitor_cap"]:
                self._beacon_visitor.clear()
            hits.append(now)
            self._beacon_visitor[h] = hits
            self._beacon_global.append(now)
            day = self._today
            self._add_visitor(ip, user_agent)
            if template in day.pages or len(day.pages) < cfg["page_max_tracked"]:
                day.pages[template] = day.pages.get(template, 0) + 1
            else:
                day.truncated["pages"] += 1
            self._maybe_flush()
        return "accepted"

    def summary(self) -> dict[str, Any]:
        with self._lock:
            self._roll()
            return {
                "since_process_start": self.process_started_at,
                "note": ("counts are in memory and cover this process only; a restart resets "
                         "them, so a low number after process_started_at is not zero traffic"),
                "persisted_to_disk": self._receipt_dir() is not None,
                "today": self._today.to_dict(live=True),
                "previous_days_this_process": list(self._history),
            }

    # -- receipt file ---------------------------------------------------------
    @staticmethod
    def _receipt_dir() -> Optional[Path]:
        raw = os.environ.get(ENV_DIR, "").strip()
        if not raw:
            return None
        p = Path(raw)
        return p if p.is_dir() else None

    def _maybe_flush(self) -> None:
        if self._receipt_dir() is None:
            return
        now = self._mono()
        if self._last_flush and now - self._last_flush < _cfg()["flush_interval_s"]:
            return
        self._last_flush = now
        self._write_receipt(self._today, force=False)

    def flush(self) -> Optional[Path]:
        with self._lock:
            self._roll()
            return self._write_receipt(self._today, force=True)

    def _write_receipt(self, day: _Day, force: bool) -> Optional[Path]:
        d = self._receipt_dir()
        if d is None:
            return None
        path = d / f"usage_{day.date}.json"
        segments: list[dict[str, Any]] = []
        try:
            if path.exists():
                prev = json.loads(path.read_text(encoding="utf-8"))
                segments = [s for s in prev.get("segments", []) if s.get("process_id") != self.process_id]
        except (OSError, ValueError):
            segments = []
        live = day is self._today and day.visitors is not None
        seg = day.to_dict(live=live)
        seg["process_id"] = self.process_id
        seg["process_started_at"] = self.process_started_at
        segments.append(seg)
        doc = {
            "date": day.date,
            "kind": "usage_receipt",
            "written_at": self._clock().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "segments": segments,
            "totals": {
                "human_requests": sum(s["human_requests"] for s in segments),
                "monitor_requests": sum(s["monitor_requests"] for s in segments),
                "bot_requests": sum(s["bot_requests"] for s in segments),
                "distinct_human_visitors_upper_bound": sum(
                    (s["distinct_human_visitors"] if isinstance(s["distinct_human_visitors"], int)
                     else _cfg()["visitor_cap"]) for s in segments),
                "visitors_note": ("sum of per-process distinct counts; visitors seen by two "
                                  "processes are counted twice (keys are not kept)"),
            },
        }
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            return None
        return path


_recorder: Optional[UsageRecorder] = None
_recorder_lock = threading.Lock()


def get_recorder() -> UsageRecorder:
    global _recorder
    with _recorder_lock:
        if _recorder is None:
            _recorder = UsageRecorder()
        return _recorder


def reset_recorder_for_tests(rec: Optional[UsageRecorder] = None) -> None:
    global _recorder
    with _recorder_lock:
        _recorder = rec
