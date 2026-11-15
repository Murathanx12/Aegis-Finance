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
  The visitor identity is HMAC-SHA256(key, ip), with a random 32-byte key
  that lives only in this process and is REPLACED at every UTC day boundary. Only the set
  of hashes for the current day is held, and only its SIZE is ever reported or written.
  Hashes cannot be linked across days (new key) or restarts (new random key).

  The user agent is used ONLY to classify monitor/bot traffic, never in the visitor hash, so
  one client rotating user agents is still one visitor. The visitor figure is nonetheless an
  UPPER BOUND (`distinct_visitors_upper_bound`): one person on two networks counts twice.

MONITORS AND BOTS are excluded from the human counts and counted separately: health /
  static routes, monitor user agents (curl is what `.github/workflows/prod-monitor.yml`
  sends every 10 minutes, Mon-Fri) and obvious bots. A receipt with only monitor traffic
  shows humans = 0.

STATE EXCEPTION: CLAUDE.md says services keep no mutable global state except cache. This module
  is a declared exception -- observability counters, in memory, with every table capped
  (`config["usage_receipt"]`), holding no identifier beyond the current day's hash set.

SERVER-SIDE CALLERS: requests the frontend host (Vercel) makes server-side to this API arrive
  from a shared address with a non-browser user agent. Unless excluded they would count as
  humans; `exclude_ua_substrings` / `exclude_ip_prefixes` in the config (empty by default)
  move such callers to the `excluded` class.

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

HUMAN, MONITOR, BOT, EXCLUDED = "human", "monitor", "bot", "excluded"

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


def resolve_client(headers: Any, peer: Optional[str]) -> tuple[str, str, int]:
    """(address, source, n_xff_entries). Source is "x-real-ip" or "peer".

    Railway documents `X-Real-IP` as the client address. `X-Forwarded-For` is deliberately NOT
    used: the rightmost entry is the hop nearest Railway, which can be an edge/CDN address, so
    every visitor would collapse into one. The value is hashed by the caller, never stored.
    """
    real = (headers.get("x-real-ip") or "").strip() if headers is not None else ""
    xff = (headers.get("x-forwarded-for") or "") if headers is not None else ""
    n_xff = len([p for p in xff.split(",") if p.strip()]) if xff else 0
    if real:
        return real, "x-real-ip", n_xff
    return peer or "", "peer", n_xff


def client_ip(headers: Any, peer: Optional[str]) -> str:
    return resolve_client(headers, peer)[0]


def classify(path: str, user_agent: str, ip: str = "") -> str:
    """human | monitor | bot | excluded, from the path, user agent and (never stored) address."""
    cfg = _cfg()
    ua_l = (user_agent or "").lower()
    if any(m and m.lower() in ua_l for m in cfg["exclude_ua_substrings"]):
        return EXCLUDED
    if ip and any(m and ip.startswith(m) for m in cfg["exclude_ip_prefixes"]):
        return EXCLUDED
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
        self.excluded_requests = 0
        self.human_requests = 0
        self.address_shape: dict[str, int] = {}
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
        shown = {t: c for t, c in self.tickers.items() if c >= cfg["ticker_min_requests"]}
        enough = isinstance(n, int) and not self.capped and n < cfg["ticker_min_visitors"]
        if enough:  # too few distinct visitors: a ticker row would describe one person
            shown = {}
        top = sorted(shown.items(), key=lambda kv: (-kv[1], kv[0]))[: cfg["ticker_top_n"]]
        suppressed = len(self.tickers) - len(top)
        return {
            "date": self.date,
            "human_requests": self.human_requests,
            "monitor_requests": self.monitor_requests,
            "bot_requests": self.bot_requests,
            "excluded_requests": self.excluded_requests,
            "distinct_visitors_upper_bound": f">={cap}" if self.capped else n,
            "distinct_visitors_capped": self.capped,
            "routes": {k: dict(sorted(v.items())) for k, v in sorted(self.requests.items())},
            "tickers_top": [{"ticker": t, "requests": c} for t, c in top],
            "tickers_suppressed_rows": suppressed,
            "address_header_shape": dict(sorted(self.address_shape.items())),
            "pageviews": dict(sorted(self.pages.items())),
            "dropped_new_keys_over_cap": dict(self.truncated),
        }


class UsageRecorder:
    def __init__(self, clock: Callable[[], datetime] = _utc_now,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._mono = monotonic
        self._lock = threading.Lock()      # guards the counters; never held across file I/O
        self._io_lock = threading.Lock()   # serialises receipt-file read-merge-write
        started = clock()
        self.process_started_at = started.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.process_id = uuid.uuid4().hex[:12]  # random, identifies a process segment only
        self._today = _Day(started.strftime("%Y-%m-%d"))
        self._history: list[dict[str, Any]] = []
        self._last_flush = 0.0
        self._pending: list[tuple[str, dict[str, Any], str]] = []
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
            self._queue_write(old, live=False)

    def _hash(self, ip: str) -> bytes:
        return hmac.new(self._today.key or b"", ip.encode(), hashlib.sha256).digest()

    def _add_visitor(self, ip: str) -> bytes:
        h = self._hash(ip)
        vs = self._today.visitors
        if vs is not None and h not in vs:
            if len(vs) >= _cfg()["visitor_cap"]:
                self._today.capped = True
            else:
                vs.add(h)
        return h

    def _queue_write(self, day: _Day, live: bool) -> None:
        seg = day.to_dict(live=live)
        seg["process_id"] = self.process_id
        seg["process_started_at"] = self.process_started_at
        self._pending.append((day.date, seg, self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")))

    def _maybe_queue_flush(self) -> None:
        # interval first: no filesystem call on the request path until a flush is due
        now = self._mono()
        if self._last_flush and now - self._last_flush < _cfg()["flush_interval_s"]:
            return
        if not os.environ.get(ENV_DIR, "").strip():
            return
        self._last_flush = now
        self._queue_write(self._today, live=True)

    def _take_pending(self) -> list[tuple[str, dict[str, Any], str]]:
        out, self._pending = self._pending, []
        return out

    # -- public ---------------------------------------------------------------
    def record_request(self, *, route: Optional[str], path_params: dict[str, Any],
                       status: int, ip: str, user_agent: str, raw_path: str,
                       addr_source: str = "peer", n_xff: int = 0) -> str:
        """Count one request. Returns its class. `route` is the matched template or None."""
        cfg = _cfg()
        kind = classify(raw_path, user_agent, ip)
        with self._lock:
            self._roll()
            day = self._today
            shape = day.address_shape
            for k in (f"used_{addr_source}", f"xff_entries_{min(n_xff, 5)}"):
                shape[k] = shape.get(k, 0) + 1
            if kind == MONITOR:
                day.monitor_requests += 1
            elif kind == BOT:
                day.bot_requests += 1
            elif kind == EXCLUDED:
                day.excluded_requests += 1
            else:
                day.human_requests += 1
                self._add_visitor(ip)
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
            self._maybe_queue_flush()
            pending = self._take_pending()
        self._write_all(pending)
        return kind

    def record_pageview(self, template: str, ip: str, user_agent: str) -> str:
        """Count a beacon page view. Returns accepted | rate_limited | bot."""
        cfg = _cfg()
        kind = classify("/api/usage/pageview", user_agent, ip)
        with self._lock:
            self._roll()
            if kind != HUMAN:
                if kind == EXCLUDED:
                    self._today.excluded_requests += 1
                else:
                    self._today.bot_requests += 1
                outcome = "bot"
            else:
                outcome = "accepted"
                now = self._mono()
                self._beacon_global = [t for t in self._beacon_global if now - t < 60]
                h = self._hash(ip)  # same identity as the visitor set: UA rotation does not help
                hits = [t for t in self._beacon_visitor.get(h, []) if now - t < 60]
                if len(self._beacon_global) >= cfg["beacon_global_per_min"]:
                    outcome = "rate_limited"
                elif len(hits) >= cfg["beacon_per_visitor_per_min"]:
                    self._beacon_visitor[h] = hits
                    outcome = "rate_limited"
                else:
                    if len(self._beacon_visitor) > cfg["visitor_cap"]:
                        self._beacon_visitor.clear()
                    hits.append(now)
                    self._beacon_visitor[h] = hits
                    self._beacon_global.append(now)
                    day = self._today
                    self._add_visitor(ip)
                    if template in day.pages or len(day.pages) < cfg["page_max_tracked"]:
                        day.pages[template] = day.pages.get(template, 0) + 1
                    else:
                        day.truncated["pages"] += 1
                    self._maybe_queue_flush()
            pending = self._take_pending()
        self._write_all(pending)
        return outcome

    def summary(self) -> dict[str, Any]:
        with self._lock:
            self._roll()
            body = {
                "since_process_start": self.process_started_at,
                "note": ("counts are in memory and cover this process only; a restart resets "
                         "them, so a low number after process_started_at is not zero traffic. "
                         "Server-side requests made by the frontend host would count as humans "
                         "unless excluded via exclude_ua_substrings / exclude_ip_prefixes"),
                "today": self._today.to_dict(live=True),
                "previous_days_this_process": list(self._history),
            }
            pending = self._take_pending()
        self._write_all(pending)
        body["persisted_to_disk"] = self._receipt_dir() is not None
        return body

    # -- receipt file (never under the counter lock) ---------------------------
    @staticmethod
    def _receipt_dir() -> Optional[Path]:
        raw = os.environ.get(ENV_DIR, "").strip()
        if not raw:
            return None
        p = Path(raw)
        return p if p.is_dir() else None

    def flush(self) -> Optional[Path]:
        with self._lock:
            self._roll()
            self._queue_write(self._today, live=True)
            pending = self._take_pending()
        return self._write_all(pending)

    def _write_all(self, pending: list[tuple[str, dict[str, Any], str]]) -> Optional[Path]:
        last: Optional[Path] = None
        for date, seg, written_at in pending:
            last = self._write_receipt(date, seg, written_at) or last
        return last

    def _write_receipt(self, date: str, seg: dict[str, Any], written_at: str) -> Optional[Path]:
        d = self._receipt_dir()
        if d is None:
            return None
        path = d / f"usage_{date}.json"
        with self._io_lock:
            segments: list[dict[str, Any]] = []
            try:
                if path.exists():
                    prev = json.loads(path.read_text(encoding="utf-8"))
                    segments = [x for x in prev.get("segments", []) if x.get("process_id") != self.process_id]
            except (OSError, ValueError):
                segments = []
            segments.append(seg)
            cap = _cfg()["visitor_cap"]
            doc = {
                "date": date,
                "kind": "usage_receipt",
                "written_at": written_at,
                "segments": segments,
                "totals": {
                    "human_requests": sum(x["human_requests"] for x in segments),
                    "monitor_requests": sum(x["monitor_requests"] for x in segments),
                    "bot_requests": sum(x["bot_requests"] for x in segments),
                    "excluded_requests": sum(x.get("excluded_requests", 0) for x in segments),
                    "distinct_visitors_upper_bound": sum(
                        (x["distinct_visitors_upper_bound"]
                         if isinstance(x["distinct_visitors_upper_bound"], int) else cap)
                        for x in segments),
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
