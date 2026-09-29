"""The deterministic reader: Murat's signed-in Chrome -> stored article, no LLM.

Verb route only (`openclaw_client.browser` / `read_text` / `open_from_tab`);
never `openclaw_client.agent`. No model decides where the browser goes, so the
browser can only go where this file says.

MURAT'S COMPLAINT, AND THE RULE IT BECAME
========================================
"it uses wrong links; scan the page and click on links." An agent that
composes a URL from what it expects a site to look like lands on a 404 or the
wrong article. So `read_listing` takes a snapshot of the LIVE page and chooses
links only from the links that page actually shows (`snapshot --format ai
--urls` gives each link's text, ref and destination). A URL this module never
saw on a page is never followed, except the listing URL the caller names.

WHERE THE BROWSER MAY GO (config, enforced in `openclaw_client` too)
===================================================================
* Hosts: `config.OPENCLAW_USER_TAB_HOSTS` -- wsj.com, barrons.com,
  marketwatch.com. Nothing else, including sec.gov/x.com/reddit/Yahoo, which
  go through their HTTP APIs or the managed profile.
* Never a `button`, `textbox`, `combobox` or form ref; never a link whose text
  reads like an account or money action (`DENY_LINK_TEXT`); never
  mail.google.com, app.alpaca.markets, railway.com, web.whatsapp.com.
* Human pace (`Throttle`): a JITTERED gap of 20-90 s between page loads
  (never the same interval twice), <= 30/h, <= 120/day, <= 40/day per host,
  persisted across processes, so two runs cannot add up to a burst; ONE
  reading session at a time (`_reader.lock`); each article is scrolled through
  in 2-3 PageDown steps with 1-3 s pauses before it is read; every session
  writes `footprint_receipt()` (gap histogram, CV, pages/hour, scroll share,
  ALARM when the CV of gaps < 0.15). Two hits on the SAME host are >= 60 s
  apart (the drawn target x3, `min_same_host_gap_s`), so a rotation down to
  one lane still paces that host.

TAB DISCIPLINE (2026-09-27, after Chrome reached 97 processes overnight with
single WSJ/Barron's renderers at 1.8-2.6 GB)
============================================================================
* After every read (text extracted and stored) the lane tab is navigated to
  `about:blank` before the next throttle sleep (`Reader.blank`); the next turn
  re-navigates it. A heavy page never sits in a waiting tab.
* A tab that has served `WEB_READER_MAX_PAGES_PER_TAB` (10) page loads is
  CLOSED and re-opened from its parent (`Reader._reopen`): a renderer does not
  return its memory on navigation alone.
* Every tab a Reader opened is in `Reader.opened`; `close_tab` records each
  close in `Reader.closed`, so a run receipt can print `orphaned_tabs`.
* `openclaw_client`'s operator guard only acts on a tab whose CURRENT host is
  wsj/barrons/marketwatch, so a blanked tab could be neither re-navigated nor
  closed through `browser()`. Since 2026-09-27 the client's guard itself
  accepts a tab THIS process opened (`_OPENED_TABS`) while it is on
  `about:blank` (re-read fresh), for `navigate` to an allowed host (landed URL
  re-read and refused off-host) or `close`; `own_blank_tab_verb` is a thin
  call to `openclaw_client.own_blank_tab`.
* `close_leftover_tabs` closes, at start-up, tabs an EARLIER run recorded as
  opened and never closed -- only session-qualified handles
  (`chrome-mcp:<nonce>:<n>`) still present on a Dow Jones host; a bare `tN`
  alias is never trusted across runs (it is reissued).

LICENCE -- quoted from the Dow Jones subscriber agreement
(https://www.dowjones.com/terms-of-use/, fetched 2026-09-26; full quotes in
`docs/research_notes/2026-09-26/research_dowjones_bundle_wsj_barrons_marketwatch.md` §5):

    9.1 "The Services are for your individual, personal and non-commercial use
        only."
    9.3 "You may occasionally download, print and/or store articles from a
        Service for your individual, personal, and non-commercial use ...
        you may not use articles you have downloaded, printed or stored to
        develop or operate an automated trading system, or for text or data
        mining any information or content (including associated metadata)."
    9.4.1 "You shall not access, view, retrieve, refresh, reload, scrape, text
        or data mine, index, process, store, harvest, or otherwise ingest the
        Services or any Content ... using any automated means, webcrawler,
        spider, script, site search/retrieval application, extension, bot,
        browser automation tool, API client, AI agent or assistant ... without
        our prior written consent."

This reader is exactly a "browser automation tool" in §9.4.1's words. It runs
only when Murat has handed the PC over (`DOWJONES_HANDOFF_FILE` exists -- his
act, never the repo's), at human pace, on his own subscription, for his own
research, and nothing it stores is republished: full text stays in the
gitignored `news_corpus/dowjones/`, and what reaches git is metadata plus the
model's own paraphrase of a claim. The primary path is the operator paste inbox
(`digest_inbox`), where a human does the reading.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from backend import config as _config
from backend.services import browser_policy as BP
from backend.services import disk_guard as DG

LICENCE = "Dow Jones subscriber, personal research; not republished"

#: Hard stop regardless of the allowlist -- the tabs open beside the reader.
NEVER_HOSTS: tuple[str, ...] = ("mail.google.com", "app.alpaca.markets", "alpaca.markets",
                                "railway.com", "railway.app", "web.whatsapp.com",
                                *BP.MESSAGE_HOSTS)
#: Roles that are never clicked. A reader clicks LINKS.
DENY_ROLES: frozenset[str] = frozenset({"button", "textbox", "combobox", "checkbox",
                                        "radio", "searchbox", "form", "menuitem",
                                        "switch", "slider", "spinbutton", "option"})
#: Link text that reads like an account, money or messaging action.
DENY_LINK_TEXT = re.compile(
    r"sign\s*(out|in|up)|log\s*(out|in)|subscribe|subscription|buy\s+now|checkout|"
    r"register|my\s+account|account|settings|newsletter|gift|manage|customer\s+center|"
    r"cancel|upgrade|offer|trial|share|email|print|comment|podcast|video", re.I)
#: The narrower deny for a company SEARCH page (2026-09-27): its links are
#: loaded by URL, never clicked, and must already match an article-id URL
#: pattern, so only text that reads like an account or money action is
#: refused. `DENY_LINK_TEXT` would drop "Viking's Trial Data ...", "... an
#: Upgrade From Analysts", "... Share Buyback" -- the news a search is for.
ARTICLE_DENY_LINK_TEXT = re.compile(
    r"sign\s*(out|in|up)|log\s*(out|in)|subscribe|subscription|buy\s+now|checkout|"
    r"register|my\s+account|customer\s+center|newsletter|gift\s+(article|subscription)", re.I)

_SNAP_NODE = re.compile(r'^\s*-\s+(\w+)\s+"((?:[^"\\]|\\.)*)"(?:.*?\[ref=([^\]]+)\])?')
_SNAP_LINK = re.compile(r"^\s*\d+\.\s+(.*?)\s+->\s+(\S+)\s*$")


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def hosts() -> tuple[str, ...]:
    """Every host the reader may load: the Dow Jones sites plus, since
    2026-09-28, the read-only social hosts (`config.OPENCLAW_BROWSER_HOSTS`)."""
    return tuple(_cfg("OPENCLAW_BROWSER_HOSTS",
                      _cfg("OPENCLAW_USER_TAB_HOSTS", ("wsj.com", "barrons.com", "marketwatch.com"))))


def social_hosts() -> tuple[str, ...]:
    return tuple(_cfg("OPENCLAW_SOCIAL_HOSTS", ("x.com", "reddit.com", "stocktwits.com")))


def is_social(url_or_host: str) -> bool:
    h = url_or_host if "://" not in (url_or_host or "") else (urlsplit(url_or_host).hostname or "")
    h = (h or "").lower()
    return any(h == d or h.endswith("." + d) for d in social_hosts())


def host_ok(url: str) -> bool:
    try:
        h = (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return False
    if not h or any(h == n or h.endswith("." + n) for n in NEVER_HOSTS):
        return False
    return any(h == d or h.endswith("." + d) for d in hosts())


#: 2026-09-26 -> 09-27: a URL with `&` used to be cut by cmd.exe inside
#: `openclaw_client._run`, so this module dropped tracking queries that carried
#: a cmd metacharacter (`shell_safe_url`). `_run` now execs node + the CLI's
#: entry script with no shell, and the URL -- query included -- is passed and
#: logged exactly as given; the drop is gone.


class ReaderRefused(RuntimeError):
    """The reader will not take this step. Never swallowed into a no-op."""


# ───────────────────────────── re-attach (J2) ───────────────────────────────
#
# 2026-09-26: `user` dropped to `stopped` BETWEEN sections -- the Chrome MCP
# subprocess dies while Chrome itself stays up with remote debugging on -- and
# the MarketWatch pass was refused. `openclaw browser --browser-profile user
# start` re-attaches to the SAME running Chrome (existing-session is
# attachOnly; it never launches a browser). A dead GATEWAY is different: the
# reader never restarts it (the operator does), it refuses by name.

#: An operator-profile error that means "detached", not "refused".
DETACHED = re.compile(r"REFUSED_BROWSER_PROFILE_UNAVAILABLE|is 'stopped'|not running|"
                      r"REFUSED_OPERATOR_TAB_MISSING|REFUSED_TABS_UNREADABLE", re.I)
#: The gateway itself is down or timing out -- never restarted from here.
GATEWAY_DOWN = re.compile(r"gateway timeout|timeout after \d+\s*ms|gateway (?:closed|"
                          r"unreachable|not running|is not running)|ECONNREFUSED", re.I)
#: `start` answered this on 2026-09-26 16:27 UTC after the MCP subprocess died:
#: the gateway cannot re-attach until IT is cleaned up (an operator restart).
#: Retrying `start` does not help, so it refuses by name at once.
GATEWAY_STUCK = re.compile(r"subprocess tree cleanup could not be verified", re.I)
REATTACH_WAIT_S = 20.0
REATTACH_POLL_S = 2.0
REATTACH_MAX_FAILURES = 2


def is_detached(msg: str) -> bool:
    return bool(DETACHED.search(msg or "")) and not GATEWAY_DOWN.search(msg or "")


def is_gateway_down(msg: str) -> bool:
    return bool(GATEWAY_DOWN.search(msg or ""))


def ensure_attached(profile: str = "muratclaw", *, oc: Any = None, log: list | None = None,
                    sleep_fn: Callable[[float], None] = time.sleep,
                    clock: Callable[[], float] = time.monotonic) -> dict:
    """The operator profile is RUNNING with tabs, re-attaching if it is not.

    `stopped` -> `browser --browser-profile <p> start`, then poll `profiles`
    and `tabs` for up to `REATTACH_WAIT_S`; a success needs state `running`
    AND a non-empty tab list. Each attempt is appended to `log`. Refuses
    `REFUSED_REATTACH_FAILED` after `REATTACH_MAX_FAILURES` failed attempts,
    and `REFUSED_GATEWAY_DOWN` at once when the gateway itself times out --
    the reader never restarts the gateway. Tab ids CHANGE after a re-attach:
    the caller re-resolves every tab it holds."""
    import subprocess
    if oc is None:
        from backend.services import openclaw_client as oc  # type: ignore[no-redef]
    log = log if log is not None else []
    # Whatever happened, the caller re-resolves its tabs next: never from a
    # cached listing taken before the detach (openclaw_client.OPENCLAW_TABS_TTL_S).
    inv = getattr(oc, "invalidate_tabs_cache", None)
    if callable(inv):
        inv(profile)

    def state() -> str | None:
        try:
            ps = oc.profiles()
        except subprocess.TimeoutExpired as exc:
            raise ReaderRefused(f"REFUSED_GATEWAY_DOWN: `browser profiles` timed out ({exc}); "
                                f"the reader does not restart the gateway") from exc
        f = next((p for p in ps if p.get("name") == profile), None)
        return f.get("state") if f else None

    st = state()
    if st == "running":
        return {"reattached": False, "state": st}
    ded = getattr(oc, "dedicated_profiles", None)
    if callable(ded) and profile in ded():
        # The dedicated Chrome is attach-only: `start` cannot bring it up. A
        # closed Chrome is a DEPENDENCY fault for the supervisor
        # (`muratclaw_instance.launch_attach`), never something the reader does.
        from backend.services import muratclaw_instance as MI
        ms = MI.status()
        if not ms.get("running_with_port"):
            raise ReaderRefused(f"REFUSED_INSTANCE_DOWN: the dedicated Chrome is not running "
                                f"with its port ({ms.get('endpoint')}); the supervisor "
                                f"launches it, the reader does not")
    if st is None:
        raise ReaderRefused(f"REFUSED_GATEWAY_DOWN: `browser profiles` did not list {profile!r} "
                            f"(gateway down or timing out?); the reader does not restart it")
    fails = 0
    while fails < REATTACH_MAX_FAILURES:
        t0 = clock()
        rc_start: int | None = None
        try:
            r = oc._run(["browser", "--browser-profile", profile, "start"], timeout=60)
            rc_start, out = r.returncode, f"{r.stdout or ''}\n{r.stderr or ''}"
        except subprocess.TimeoutExpired:
            out = "gateway timeout: `start` timed out after 60000ms"
        entry: dict[str, Any] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "profile": profile, "attempt": fails + 1, "from_state": st,
                                 "start_rc": rc_start, "start_out": out.strip()[:300]}
        if GATEWAY_STUCK.search(out):
            entry.update(ok=False, why=out.strip()[:200])
            log.append(entry)
            raise ReaderRefused(f"REFUSED_GATEWAY_DOWN: GATEWAY_NEEDS_RESTART: `start` answered "
                                f"{out.strip()[:160]!r}; the reader does not restart the gateway")
        if GATEWAY_DOWN.search(out):
            entry.update(ok=False, why=out.strip()[:200])
            log.append(entry)
            raise ReaderRefused(f"REFUSED_GATEWAY_DOWN: {out.strip()[:200]!r}; the reader does "
                                f"not restart the gateway")
        ok, n_tabs = False, 0
        while True:
            if state() == "running":
                try:
                    n_tabs = len(oc.tabs(profile_name=profile))
                except Exception:  # noqa: BLE001 -- not ready yet
                    n_tabs = 0
                if n_tabs:
                    ok = True
                    break
            if clock() - t0 >= REATTACH_WAIT_S:
                break
            sleep_fn(REATTACH_POLL_S)
        entry.update(ok=ok, tabs=n_tabs, seconds=round(clock() - t0, 1))
        log.append(entry)
        if ok:
            getattr(oc, "_ATTACHED_CACHE", {}).pop(profile, None)
            return {"reattached": True, "state": "running", "tabs": n_tabs}
        fails += 1
    raise ReaderRefused(f"REFUSED_REATTACH_FAILED: {profile!r} still not running with tabs after "
                        f"{REATTACH_MAX_FAILURES} `start` attempts ({REATTACH_WAIT_S:.0f} s each)")


# ───────────────────────────── snapshot parsing ─────────────────────────────

def parse_snapshot(text: str) -> dict:
    """`{nodes: [{role, name, ref, url}], links: [{text, url, ref}]}` from
    `snapshot --format ai --urls` output, in EITHER shape: the chrome-mcp tree
    with a `Links:` appendix, or (the attach profile, 2026-09-28) the tree with
    each link's `[url=...]` inline and no appendix. One parser for both, in
    `browser_policy`, so the click guard and the link chooser read a page the
    same way. Before this, the new driver's pages parsed as 0 links."""
    return BP.parse_snapshot(text)


def select_links(snapshot_text: str, link_pattern: str, *, text_pattern: str | None = None,
                 limit: int | None = None, deny_text: re.Pattern | None = None) -> list[dict]:
    """Links the page SHOWS that match `link_pattern` (on the URL) and, if
    given, `text_pattern` (on the link text). `[{text, url, ref}]`, deduped by
    URL, in page order. A decoy (wrong host, account/money text, a button, a
    URL that does not match) is never returned. `deny_text` defaults to
    `DENY_LINK_TEXT`."""
    snap = parse_snapshot(snapshot_text)
    link_nodes = [n for n in snap["nodes"] if n["role"] == "link" and n["ref"]]
    refs_by_text: dict[str, list[str]] = {}
    for n in link_nodes:
        refs_by_text.setdefault(n["name"], []).append(n["ref"])
    url_re = re.compile(link_pattern)
    txt_re = re.compile(text_pattern, re.I) if text_pattern else None
    out, seen = [], set()
    for lk in snap["links"]:
        u, t = lk["url"], lk["text"]
        base = u.split("#")[0]
        if base in seen or not host_ok(u) or not url_re.search(u):
            continue
        if (deny_text or DENY_LINK_TEXT).search(t) or (txt_re and not txt_re.search(t)):
            continue
        if len(t) < 12:        # section chrome ("Markets", "Tech"), not a headline
            continue
        refs = refs_by_text.get(t) or []
        seen.add(base)
        out.append({"text": t, "url": u, "ref": refs.pop(0) if refs else None})
        if limit and len(out) >= limit:
            break
    return out


def ref_is_clickable(snapshot_text: str, ref: str) -> bool:
    """A ref may be clicked only if the snapshot shows it as a LINK whose text
    is not an account/money action."""
    for n in parse_snapshot(snapshot_text)["nodes"]:
        if n["ref"] == ref:
            return n["role"] == "link" and n["role"] not in DENY_ROLES \
                and not DENY_LINK_TEXT.search(n["name"]) \
                and BP.text_refusal(n["name"]) is None \
                and not (n.get("url") and (BP.url_refusal(n["url"]) or not host_ok(n["url"])))
    return False


# ───────────────────────────────── throttle ─────────────────────────────────

@dataclass
class Throttle:
    """Human pace, persisted in a file so separate runs share one budget.

    JITTERED, not a floor (research note 2026-09-26 human-pace §5): each gap
    target is drawn from a lognormal clipped to [`min_delay_s`, `max_delay_s`]
    (20-90 s), never within 1 s of the previous target, and the realised wait
    is `max(0, target - elapsed)`. A constant interval is the machine tell the
    footprint receipt alarms on (CV of gaps < 0.15).

    Log line: `<iso> <host> <target_gap_s>`; a bare `<iso>` line (written
    before the jitter) still parses, with no host.
    """

    path: Path
    min_delay_s: float = field(default_factory=lambda: float(_cfg("WEB_READER_MIN_DELAY_S", 20.0)))
    max_delay_s: float = field(default_factory=lambda: float(_cfg("WEB_READER_MAX_DELAY_S", 90.0)))
    max_per_hour: int = field(default_factory=lambda: int(_cfg("WEB_READER_MAX_PER_HOUR", 30)))
    max_per_day: int = field(default_factory=lambda: int(_cfg("WEB_READER_MAX_PER_DAY", 120)))
    max_per_day_per_host: int = field(
        default_factory=lambda: int(_cfg("WEB_READER_MAX_PER_DAY_PER_HOST", 40)))
    #: Per-host daily caps that REPLACE `max_per_day_per_host` for a host (or a
    #: subdomain of it): the social hosts start at 150/day each (2026-09-28).
    per_host_day_caps: dict = field(
        default_factory=lambda: dict(_cfg("WEB_READER_MAX_PER_DAY_BY_HOST", {}) or {}))
    #: Two page loads on the SAME host are at least this far apart: the drawn
    #: target SCALED by `min_same_host_gap_s / min_delay_s` (60/20 = 3x, so a
    #: one-lane run gaps in [60, 270] s). Scaled, not shifted: `60 + jitter`
    #: cut the CV of gaps to ~0.10 and tripped the footprint's constant-pace
    #: ALARM in the test. The rotation interleaves hosts; with one lane left
    #: this still paces that host.
    min_same_host_gap_s: float = field(
        default_factory=lambda: float(_cfg("WEB_READER_MIN_SAME_HOST_GAP_S", 60.0)))
    now_fn: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))
    sleep_fn: Callable[[float], None] = field(default=time.sleep)
    seed: int | None = None
    #: A long unattended run (`dowjones_pull --plan/--archive/--queue`) WAITS
    #: out the hourly cap instead of stopping: it sleeps until the oldest load
    #: in the window is an hour old, plus a jittered 5-60 s. The daily and
    #: per-host daily caps still refuse. A wait longer than
    #: `max_hour_wait_s` refuses rather than sleeping indefinitely.
    wait_on_hour_cap: bool = False
    max_hour_wait_s: float = 3900.0
    hour_cap_waits: list[float] = field(default_factory=list)
    #: `[{host, extra_s}]`: each time the same-host floor, not the shared
    #: jittered gap, set the wait.
    same_host_waits: list[dict] = field(default_factory=list)
    waits: list[float] = field(default_factory=list)
    targets: list[float] = field(default_factory=list)
    #: slots given back by `refund` (an open that loaded no page)
    refunds: list[dict] = field(default_factory=list)
    #: PER-HOST PACING (the reader pool, 2026-09-28 21:45 HKT; Murat: "this one
    #: by one is very slow"). Off by default: every existing caller keeps the
    #: global drawn gap above. On: a page OPEN on host h waits for h's own drawn
    #: gap (`host_gap_s[h]`, a right-skewed draw inside (lo, hi), never within
    #: 1 s of h's previous draw) and for a short drawn gap after ANY open
    #: (`global_gap_s`). The slot is RESERVED (a future-dated line) under the
    #: file lock and slept OUTSIDE it, so a worker waiting for one host never
    #: holds up a worker bound for another. Hourly caps per host
    #: (`per_host_hour_caps`) bind inside `max_per_hour`.
    per_host_mode: bool = False
    host_gap_s: dict = field(default_factory=lambda: dict(_cfg("READER_HOST_GAP_S", {}) or {}))
    global_gap_s: tuple = field(
        default_factory=lambda: tuple(_cfg("READER_GLOBAL_GAP_S", (1.0, 4.0))))
    per_host_hour_caps: dict = field(
        default_factory=lambda: dict(_cfg("READER_MAX_PER_HOUR_BY_HOST", {}) or {}))
    host_targets: dict = field(default_factory=dict)
    _rng: Any = field(default=None, repr=False)
    _last_line: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import numpy as np
        self._rng = np.random.default_rng(self.seed)

    def _rows(self) -> list[tuple[datetime, str, float | None]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split()
            if not parts:
                continue
            try:
                t = datetime.fromisoformat(parts[0])
            except ValueError:
                continue
            host = parts[1] if len(parts) > 1 else ""
            try:
                tgt = float(parts[2]) if len(parts) > 2 else None
            except ValueError:
                tgt = None
            out.append((t, host, tgt))
        return out

    def _stamps(self) -> list[datetime]:
        return [r[0] for r in self._rows()]

    def draw_target(self, previous: float | None) -> float:
        lo, hi = float(self.min_delay_s), float(max(self.max_delay_s, self.min_delay_s))
        if hi <= lo:
            return lo
        for _ in range(20):
            # lognormal centred ~35 s with a long right tail, clipped to [lo, hi]
            x = float(min(hi, max(lo, lo + self._rng.lognormal(mean=2.7, sigma=0.7))))
            if previous is None or abs(x - previous) >= 1.0:
                return round(x, 2)
        return round(lo + (hi - lo) * float(self._rng.random()), 2)

    def lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    def host_day_cap(self, host: str) -> int:
        """The daily cap for `host`: a `per_host_day_caps` entry matching the host
        or a parent domain of it, else `max_per_day_per_host`."""
        h = (host or "").lower().removeprefix("www.")
        for d, cap in (self.per_host_day_caps or {}).items():
            if h == d or h.endswith("." + d):
                return int(cap)
        return int(self.max_per_day_per_host)

    def last_load_by_host(self) -> dict[str, datetime]:
        """host -> the time of its most recent load (for `pick_next_lane`)."""
        out: dict[str, datetime] = {}
        for t, h, _ in self._rows():
            if h and h != "-" and (h not in out or t > out[h]):
                out[h] = t
        return out

    def acquire(self, what: str = "page", host: str = "") -> float:
        """Sleep until the next load is allowed, record it, return seconds waited.
        Raises `ReaderRefused` when the hourly, daily or per-host daily cap is spent.

        The whole read -> wait -> append runs under `disk_guard.file_lock` on
        `<throttle>.lock` (2026-09-27): with several reader processes sharing
        this file, two of them reading the same "last load" would both take
        the same slot. The lock is held THROUGH the sleep, so the next taker
        computes its gap from the stamp this one writes.

        `per_host_mode`: the slot is RESERVED under the lock and slept outside
        it (`reserve`)."""
        if self.per_host_mode:
            res = self.reserve(what, host)
            if res["wait_s"] > 0:
                self.sleep_fn(res["wait_s"])
            return float(res["wait_s"])
        with DG.file_lock(self.lock_path()):
            return self._acquire(what, host)

    # ── per-host pacing (the reader pool, 2026-09-28) ───────────────────────

    def draw_between(self, lo: float, hi: float, previous: float | None) -> float:
        """A gap inside [lo, hi]: right-skewed (beta(2, 3.5), mean ~36% of the
        range), never clipped to an edge, never within 1 s of `previous`."""
        lo, hi = float(lo), float(max(hi, lo))
        if hi <= lo:
            return round(lo, 2)
        for _ in range(20):
            x = lo + (hi - lo) * float(self._rng.beta(2.0, 3.5))
            if previous is None or abs(x - previous) >= 1.0 or hi - lo < 2.0:
                return round(x, 2)
        return round(lo + (hi - lo) * float(self._rng.random()), 2)

    def host_range(self, host: str) -> tuple[float, float]:
        """(lo, hi) of `host`'s drawn gap (a parent-domain entry matches)."""
        h = (host or "").lower().removeprefix("www.")
        for d, rng in (self.host_gap_s or {}).items():
            if h == d or h.endswith("." + d):
                return float(rng[0]), float(rng[1])
        return float(self.min_delay_s), float(max(self.max_delay_s, self.min_delay_s))

    def host_hour_cap(self, host: str) -> int | None:
        h = (host or "").lower().removeprefix("www.")
        for d, cap in (self.per_host_hour_caps or {}).items():
            if h == d or h.endswith("." + d):
                return int(cap)
        return None

    def next_free_at(self, host: str) -> datetime:
        """PEEK (no lock, no write): the earliest a page open on `host` could be
        reserved, from the LOW end of each drawn range. The pool's scheduler
        prefers a host that is free now over one it would have to wait for."""
        rows = self._rows()
        at = self.now_fn()
        same = [r[0] for r in rows if host and r[1] == host]
        if same:
            at = max(at, max(same) + timedelta(seconds=self.host_range(host)[0]))
        return fit_global_gap(at, [r[0] for r in rows], float(self.global_gap_s[0]))

    def reserve(self, what: str = "page", host: str = "") -> dict:
        """Reserve the next page-open slot on `host` under the file lock and
        return `{line, slot, wait_s, target_s, global_s}` WITHOUT sleeping (the
        caller sleeps `wait_s` outside the lock; `acquire` does exactly that).
        The daily caps refuse. The hourly caps (all hosts, and this host's) are
        waited out when `wait_on_hour_cap` -- the slot moves to when the window
        frees, plus a drawn 5-60 s, up to `max_hour_wait_s` -- else refuse."""
        with DG.file_lock(self.lock_path()):
            return self._reserve(what, host)

    def _reserve(self, what: str, host: str) -> dict:
        now = self.now_fn()
        rows = [r for r in self._rows() if now - r[0] < timedelta(days=1)]
        if len(rows) >= self.max_per_day:
            raise ReaderRefused(f"REFUSED_THROTTLE_DAY: {len(rows)} page loads in 24 h "
                                f">= {self.max_per_day}")
        cap = self.host_day_cap(host)
        if host and sum(1 for r in rows if r[1] == host) >= cap:
            raise ReaderRefused(f"REFUSED_THROTTLE_HOST_DAY: >= {cap} "
                                f"page loads on {host} in 24 h")
        lo, hi = self.host_range(host)
        prev_t = self.host_targets.get(host)
        if prev_t is None:
            prev_t = next((r[2] for r in reversed(rows) if r[1] == host and r[2] is not None),
                          None)
        target = self.draw_between(lo, hi, prev_t)
        g = self.draw_between(float(self.global_gap_s[0]), float(self.global_gap_s[1]), None)
        slot = now
        same = [r[0] for r in rows if host and r[1] == host]
        if same:
            slot = max(slot, max(same) + timedelta(seconds=target))
        # the global gap keeps any two opens `g` apart; it does NOT queue this
        # host behind a FUTURE-dated reservation of another host (2026-09-29:
        # x.com's hourly cap reserved a slot 10 min ahead and every host --
        # wsj, barrons, marketwatch included -- queued behind it: 10 idle min)
        all_stamps = [r[0] for r in rows]
        slot = fit_global_gap(slot, all_stamps, g)
        hcap = self.host_hour_cap(host)
        for _ in range(50):
            # every open stamped after (slot - 1 h), reservations beyond `slot` included
            win = [r for r in rows if r[0] > slot - timedelta(hours=1)]
            win_h = [r for r in win if host and r[1] == host]
            full_all = len(win) >= self.max_per_hour
            full_h = bool(host) and hcap is not None and len(win_h) >= hcap
            if not (full_all or full_h):
                break
            if not self.wait_on_hour_cap:
                what_cap = (f"{self.max_per_hour} page loads" if full_all else
                            f"{hcap} page loads on {host}")
                raise ReaderRefused(f"REFUSED_THROTTLE_HOUR: >= {what_cap} in the last hour")
            stamps = sorted(r[0] for r in (win if full_all else win_h))
            k = len(stamps) - (self.max_per_hour if full_all else int(hcap or 0))
            free_at = stamps[max(0, k)] + timedelta(hours=1)
            slot = max(slot, free_at) + timedelta(seconds=float(self._rng.uniform(5.0, 60.0)))
            slot = fit_global_gap(slot, all_stamps, g)
            pause = (slot - now).total_seconds()
            if pause > self.max_hour_wait_s:
                raise ReaderRefused(f"REFUSED_THROTTLE_HOUR: the hourly cap would need a "
                                    f"{pause:.0f} s wait > {self.max_hour_wait_s:.0f} s")
            self.hour_cap_waits.append(round(pause, 1))
        wait = max(0.0, (slot - now).total_seconds())
        self.host_targets[host] = target
        self.targets.append(target)
        self.waits.append(round(wait, 2))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = f"{slot.isoformat()} {host or '-'} {target}"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self._last_line = line
        return {"line": line, "slot": slot, "wait_s": round(wait, 3), "target_s": target,
                "global_s": g, "what": what, "host": host}

    def _acquire(self, what: str, host: str) -> float:
        now = self.now_fn()
        rows = [r for r in self._rows() if now - r[0] < timedelta(days=1)]
        if len(rows) >= self.max_per_day:
            raise ReaderRefused(f"REFUSED_THROTTLE_DAY: {len(rows)} page loads in 24 h "
                                f">= {self.max_per_day}")
        cap = self.host_day_cap(host)
        if host and sum(1 for r in rows if r[1] == host) >= cap:
            raise ReaderRefused(f"REFUSED_THROTTLE_HOST_DAY: >= {cap} "
                                f"page loads on {host} in 24 h")
        while sum(1 for r in rows if now - r[0] < timedelta(hours=1)) >= self.max_per_hour:
            if not self.wait_on_hour_cap:
                raise ReaderRefused(f"REFUSED_THROTTLE_HOUR: >= {self.max_per_hour} page loads "
                                    f"in the last hour")
            in_hour = sorted(r[0] for r in rows if now - r[0] < timedelta(hours=1))
            k = len(in_hour) - self.max_per_hour      # this many must age out first
            free_at = in_hour[k] + timedelta(hours=1)
            pause = (free_at - now).total_seconds() + float(self._rng.uniform(5.0, 60.0))
            if pause > self.max_hour_wait_s:
                raise ReaderRefused(f"REFUSED_THROTTLE_HOUR: the hourly cap would need a "
                                    f"{pause:.0f} s wait > {self.max_hour_wait_s:.0f} s")
            self.sleep_fn(pause)
            self.hour_cap_waits.append(round(pause, 1))
            now = self.now_fn()
            rows = [r for r in self._rows() if now - r[0] < timedelta(days=1)]
        prev = next((r[2] for r in reversed(rows) if r[2] is not None), None)
        target = self.draw_target(self.targets[-1] if self.targets else prev)
        wait = 0.0
        if rows:
            gap = (now - max(r[0] for r in rows)).total_seconds()
            wait = max(0.0, target - gap)
        same = [r[0] for r in rows if host and r[1] == host]
        if same and self.min_same_host_gap_s > 0:
            k = self.min_same_host_gap_s / max(float(self.min_delay_s), 1.0)
            floor = max(self.min_same_host_gap_s, target * max(1.0, k))
            need = floor - (now - max(same)).total_seconds()
            if need > wait:
                self.same_host_waits.append({"host": host, "extra_s": round(need - wait, 2)})
                wait = need
        if wait > 0:
            self.sleep_fn(wait)
        self.waits.append(round(wait, 2))
        self.targets.append(target)
        stamp = self.now_fn() if wait > 0 else now
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = f"{stamp.isoformat()} {host or '-'} {target}"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self._last_line = line
        return wait

    def refund(self, why: str = "", *, line: str | None = None) -> bool:
        """Give back the slot the LAST `acquire` of this object took (2026-09-28),
        or, with `line`, the slot whose throttle line that is (a lane's own load
        in an interleaved rotation, where another lane may have acquired since).

        A tab open that failed before any page loaded -- a pop-up blocked, a
        gateway refusal, an instance refusal -- loaded nothing, so it must not
        count against the hourly, daily or per-host caps: on 2026-09-28 sixteen
        slots were burnt by opens that never produced a tab. Removes exactly
        the line that acquire wrote (under the same file lock), once; returns
        whether it was found. The pacing wait already slept is not undone."""
        if line is None:
            line = self._last_line
            if not line:
                return False
            self._last_line = None
        elif line == self._last_line:
            self._last_line = None
        with DG.file_lock(self.lock_path()):
            try:
                rows = self.path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return False
            for i in range(len(rows) - 1, -1, -1):
                if rows[i].strip() == line:
                    del rows[i]
                    break
            else:
                return False
            if rows:
                DG.atomic_write_text(self.path, "".join(r + "\n" for r in rows))
            else:   # the refunded line was the only one (atomic_write refuses empty)
                self.path.write_text("", encoding="utf-8")
        if self.targets:
            self.targets.pop()
        self.refunds.append({"line": line, "why": str(why)[:160]})
        return True


def fit_global_gap(slot: datetime, stamps: list[datetime], gap_s: float) -> datetime:
    """PURE. The earliest time >= `slot` that is at least `gap_s` from every
    stamp in `stamps` (past opens and future reservations alike). A free
    interval BEFORE a future reservation is used; the slot is not pushed behind
    the latest reservation of every host."""
    g = timedelta(seconds=float(gap_s))
    for s in sorted(stamps):
        if s - g < slot < s + g:
            slot = s + g
    return slot


def throttle_path() -> Path:
    return corpus_root() / "_throttle.log"


# ─────────────────────────── one reader at a time ───────────────────────────

def lock_path() -> Path:
    return corpus_root() / "_reader.lock"


def _pid_alive(pid: int) -> bool:
    import os
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            return code.value == 259  # STILL_ACTIVE
        os.kill(pid, 0)
        return True
    except OSError:
        return False


_WORKER_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def worker_lock_path(worker: str) -> Path:
    """`_reader_<worker>.lock` -- one per worker id (2026-09-27)."""
    if not _WORKER_ID.match(str(worker or "")):
        raise ReaderRefused(f"REFUSED_WORKER_ID: {worker!r} is not [a-z0-9_-]{{1,32}}")
    return corpus_root() / f"_reader_{worker}.lock"


def _live_holder(p: Path, me: int) -> dict | None:
    """The lock file's holder when it is a LIVE process other than `me`."""
    if not p.exists():
        return None
    try:
        other = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    opid = int(other.get("pid") or 0)
    if opid and opid != me and _pid_alive(opid):
        return {"pid": opid, "since": other.get("since"), "path": str(p)}
    return None


def live_reader_locks(*, me: int | None = None) -> list[dict]:
    """Every reader lock (the single-session one and every worker's) held by a
    live process other than `me`."""
    import os
    me = int(me if me is not None else os.getpid())
    root = corpus_root()
    paths = [lock_path(), *sorted(root.glob("_reader_*.lock"))] if root.exists() else []
    return [h for h in (_live_holder(p, me) for p in paths) if h]


def acquire_reader_lock(path: Path | None = None, *, pid: int | None = None,
                        worker: str | None = None) -> Path:
    """ONE reading session at a time, across processes. A lock whose PID is
    dead is stale and is taken over (and said so in the lock itself).

    WORKERS (2026-09-27). `worker="wsj"` takes `_reader_wsj.lock` instead: one
    live process per worker id, several worker ids at once. A worker refuses
    while a single-session reader (`_reader.lock`) is live, and a
    single-session reader (no `worker`, no explicit `path`) refuses while ANY
    worker is live -- the two modes never overlap. An explicit `path` checks
    only that path (the old contract)."""
    import os
    me = int(pid if pid is not None else os.getpid())
    if worker is not None:
        p = worker_lock_path(worker)
        others = [h for h in (_live_holder(lock_path(), me), _live_holder(p, me)) if h]
    elif path is not None:
        p = Path(path)
        others = [h for h in (_live_holder(p, me),) if h]
    else:
        p = lock_path()
        others = live_reader_locks(me=me)
    if others:
        o = others[0]
        raise ReaderRefused(f"REFUSED_READER_BUSY: another reading session (pid {o['pid']}, "
                            f"since {o.get('since')}) holds {o['path']}")
    DG.atomic_write_json(p, {"pid": me, "since": datetime.now(timezone.utc).isoformat(
        timespec="seconds"), **({"worker": worker} if worker else {})},
        indent=None, ensure_ascii=True)
    return p


def release_reader_lock(path: Path | None = None, *, pid: int | None = None) -> None:
    import os
    p = Path(path) if path else lock_path()
    me = int(pid if pid is not None else os.getpid())
    try:
        if p.exists() and int(json.loads(p.read_text(encoding="utf-8")).get("pid") or 0) == me:
            p.unlink()
    except (OSError, ValueError):
        pass


# ───────────────────────────── footprint receipt ────────────────────────────

FOOTPRINT_CV_ALARM = 0.15


def _ledger_now() -> dict | None:
    try:
        from backend.services import openclaw_client as OC
        return OC.cli_ledger()
    except Exception:  # noqa: BLE001 -- a receipt must still be written
        return None


def cli_footprint(now: dict | None, since: dict | None, pages: int, *,
                  scope: str) -> dict:
    """What the session cost in OpenClaw CLI round trips (2026-09-27: ~15 s
    each under memory pressure). `now - since` from `openclaw_client.cli_ledger()`:
    `cli_calls`, `cli_seconds`, `cli_seconds_per_page`, and `cli_breakdown`
    split into `profile_check` (`browser profiles`), `tabs_listing` (`browser
    tabs`) and `other`, plus the cache counters. `scope` says what the delta
    covers -- the ledger is per PROCESS, so a reader's delta includes any
    other lane driven by the same process in the same window."""
    if not now:
        return {"cli_scope": scope, "cli_calls": None, "cli_seconds": None,
                "cli_seconds_per_page": None, "cli_breakdown": None, "cli_cache": None,
                "cli_by_verb": None,
                "cli_ledger": "UNAVAILABLE: the driver has no cli_ledger()"}
    base = since or {"calls": 0, "seconds": 0.0, "by_cmd": {}, "cache": {}}

    def row(key: str) -> dict:
        a = (now.get("by_cmd") or {}).get(key) or {}
        b = (base.get("by_cmd") or {}).get(key) or {}
        return {"calls": int(a.get("calls", 0)) - int(b.get("calls", 0)),
                "seconds": round(float(a.get("seconds", 0.0)) - float(b.get("seconds", 0.0)), 3)}

    calls = int(now.get("calls", 0)) - int(base.get("calls", 0))
    secs = round(float(now.get("seconds", 0.0)) - float(base.get("seconds", 0.0)), 3)
    prof, tabl = row("browser profiles"), row("browser tabs")
    other = {"calls": calls - prof["calls"] - tabl["calls"],
             "seconds": round(secs - prof["seconds"] - tabl["seconds"], 3)}
    cache = {k: int(v) - int((base.get("cache") or {}).get(k, 0))
             for k, v in (now.get("cache") or {}).items()}
    # seconds per VERB (2026-09-27): the 3-way breakdown could not say where
    # "other" went, so a profile of a night had to be rebuilt from the code
    by_verb = {k: row(k) for k in sorted(now.get("by_cmd") or {})}
    by_verb = {k: dict(v, s_per_call=round(v["seconds"] / v["calls"], 2))
               for k, v in by_verb.items() if v["calls"] > 0}
    return {"cli_scope": scope, "cli_calls": calls, "cli_seconds": secs,
            "cli_seconds_per_page": round(secs / pages, 3) if pages else None,
            "cli_calls_per_page": round(calls / pages, 2) if pages else None,
            "cli_breakdown": {"profile_check": prof, "tabs_listing": tabl, "other": other},
            "cli_cache": cache, "cli_by_verb": by_verb}


def footprint_receipt(log: list[dict], *, scrolled: int = 0, reads: int = 0,
                      out_dir: Path | None = None, write: bool = True,
                      cli_now: dict | None = None, cli_since: dict | None = None) -> dict:
    """What this session looked like from the site's side: the gaps between
    page loads, pages/hour, the coefficient of variation of the gaps, and the
    share of reads that scrolled. `verdict` is `HUMAN_PACE_OK`, `ALARM: ...`
    (CV < 0.15 -- pacing collapsed to a constant) or `CANNOT DETERMINE` (< 3
    gaps), never a bare boolean.

    It also carries the CLI cost (`cli_footprint`): `cli_now` defaults to this
    process's `openclaw_client.cli_ledger()`, and `cli_since` to nothing, so a
    caller with no baseline gets the whole process (`cli_scope: "process"`)."""
    import statistics as stats
    stamps = sorted(datetime.fromisoformat(p["at"]) for p in log if p.get("at"))
    gaps = [round((b - a).total_seconds(), 1) for a, b in zip(stamps, stamps[1:])]
    span_h = ((stamps[-1] - stamps[0]).total_seconds() / 3600) if len(stamps) > 1 else 0.0
    cv = (stats.pstdev(gaps) / stats.mean(gaps)) if len(gaps) >= 2 and stats.mean(gaps) > 0 else None
    bins = [(0, 20), (20, 30), (30, 45), (45, 60), (60, 90), (90, 180), (180, 600), (600, 10**9)]
    hist = {f"{lo}-{hi if hi < 10**9 else 'inf'}s": sum(1 for g in gaps if lo <= g < hi)
            for lo, hi in bins}
    if len(gaps) < 3:
        verdict = f"CANNOT DETERMINE: {len(gaps)} gap(s), need >= 3"
    elif cv is not None and cv < FOOTPRINT_CV_ALARM:
        verdict = f"ALARM: CV of gaps {cv:.3f} < {FOOTPRINT_CV_ALARM} -- pacing collapsed to a constant"
    elif min(gaps) < float(_cfg("WEB_READER_MIN_DELAY_S", 20.0)) - 1:
        verdict = f"ALARM: a gap of {min(gaps)} s is under the {_cfg('WEB_READER_MIN_DELAY_S', 20.0)} s floor"
    else:
        verdict = "HUMAN_PACE_OK"
    rc = {"receipt": "web_reader.footprint",
          "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "pages": len(stamps), "gaps_s": gaps, "gap_histogram": hist,
          "gap_mean_s": round(stats.mean(gaps), 1) if gaps else None,
          "gap_min_s": min(gaps) if gaps else None, "gap_max_s": max(gaps) if gaps else None,
          "cv_of_gaps": round(cv, 3) if cv is not None else None,
          "pages_per_hour": round(len(stamps) / span_h, 2) if span_h > 0 else None,
          "reads": reads, "reads_with_scroll": scrolled,
          "scroll_share": round(scrolled / reads, 3) if reads else None,
          "cv_alarm_threshold": FOOTPRINT_CV_ALARM, "verdict": verdict}
    rc.update(cli_footprint(cli_now if cli_now is not None else _ledger_now(), cli_since,
                            len(stamps),
                            scope="since_reader_start" if cli_since is not None else "process"))
    if write:
        d = Path(out_dir) if out_dir else Path(_config.OPTIMUS_LEDGER_DIR) / "web_reader"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"footprint_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        # atomic (2026-09-27): footprint_20260927T111242Z.json was truncated to 0 bytes
        DG.atomic_write_json(p, rc, ensure_ascii=True)
        rc["path"] = str(p)
    return rc


# ─────────────────────────────── text cleaning ──────────────────────────────

NAV_LINES = {
    "sign out", "sign in", "subscribe", "my account", "customer center", "latest",
    "home", "world", "business", "u.s.", "politics", "economy", "tech", "markets",
    "finance", "opinion", "arts", "lifestyle", "real estate", "personal finance",
    "health", "style", "sports", "search", "skip to main content", "share",
    "resize", "listen", "print", "gift unlocked article", "advertisement",
    "what to read next", "most popular news", "most popular opinion", "videos",
    "recommended videos", "show conversation", "conversation", "english edition",
    "print edition", "video", "audio", "latest headlines", "more",
}
END_MARKERS = re.compile(
    r"^(copyright ©|copyright \(c\)|appeared in the|what to read next|most popular|"
    r"further reading|show conversation|videos|recommended videos|"
    r"dow jones & company|terms of use|©\s*\d{4})", re.I)
_MONTHS = ("jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|"
           "april|june|july|august|september|october|november|december")
DATE_RE = re.compile(
    rf"\b(?:updated\s+|published\s+)?((?:{_MONTHS})\.?\s+\d{{1,2}},\s+\d{{4}})"
    rf"(?:,?\s+(?:at\s+)?(\d{{1,2}}:\d{{2}})\s*([ap])\.?m\.?\s*(ET|EDT|EST)?)?", re.I)
BYLINE_RE = re.compile(r"^By\s+[A-Z][\w.'\-]+(\s|$)")


def account_patterns() -> tuple[str, ...]:
    return tuple(_cfg("DOWJONES_ACCOUNT_NAME_PATTERNS", ("murat", "murathan", "abdullaev")))


def clean_text(text: str, title: str | None = None) -> str:
    """Strip navigation, header, footer and the account holder's name."""
    lines = [ln.strip() for ln in (text or "").splitlines()]
    acct = account_patterns()
    kept: list[str] = []
    for ln in lines:
        low = ln.lower()
        if not ln or len(ln) < 3 or low in NAV_LINES:
            continue
        if len(ln) < 60 and any(a in low for a in acct):
            continue
        kept.append(ln)
    if title:
        t = title.split(" - ")[0].split(" | ")[0].strip().lower()
        for i, ln in enumerate(kept):
            if t and (ln.lower() == t or (len(t) > 20 and t in ln.lower())):
                kept = kept[i:]
                break
    for i, ln in enumerate(kept):
        if i > 3 and END_MARKERS.match(ln):
            kept = kept[:i]
            break
    return "\n".join(kept)


def parse_published(text: str) -> str | None:
    """The first dateline in the text, as UTC ISO (ET assumed when a time is
    given, since every Dow Jones dateline is Eastern); a date alone -> 00:00 ET."""
    from zoneinfo import ZoneInfo
    m = DATE_RE.search(text or "")
    if not m:
        return None
    d = m.group(1).replace(".", "").replace("Sept ", "Sep ")
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            day = datetime.strptime(d, fmt)
            break
        except ValueError:
            day = None
    if day is None:
        return None
    hh, mm = 0, 0
    if m.group(2):
        hh, mm = (int(x) for x in m.group(2).split(":"))
        if m.group(3).lower() == "p" and hh != 12:
            hh += 12
        if m.group(3).lower() == "a" and hh == 12:
            hh = 0
    local = day.replace(hour=hh, minute=mm, tzinfo=ZoneInfo("America/New_York"))
    return local.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_byline(text: str) -> str | None:
    for ln in (text or "").splitlines()[:40]:
        if BYLINE_RE.match(ln.strip()):
            return ln.strip()[:200]
    return None


# ───────────────────────────────── storage ──────────────────────────────────

def corpus_root() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "news_corpus" / "dowjones"


def norm_url(url: str) -> str:
    """Scheme-less, query- and fragment-free, lowercase: the key a stored
    article is found by when a rotating or archive run resumes."""
    try:
        sp = urlsplit(url or "")
    except ValueError:
        return (url or "").lower()
    return f"{(sp.hostname or '').lower().removeprefix('www.')}{sp.path.rstrip('/')}".lower()


def stored_urls(root: Path | None = None) -> dict[str, set[str]]:
    """`{norm_url: {first_seen day, ...}}` over every stored article, so a
    resumed run skips what it already holds (the text sha dedupes as well;
    this skips the PAGE LOAD, which is what the site sees)."""
    root = Path(root) if root else corpus_root()
    out: dict[str, set[str]] = {}
    for p in root.glob("*/*/*.json"):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        u = rec.get("url")
        if u:
            out.setdefault(norm_url(u), set()).add(str(rec.get("first_seen_utc") or "")[:10])
    return out


def registry_source_id(publisher: str, origin: str) -> str:
    """The `news_sources.yaml` id a stored article's corpus row carries."""
    return "dj_digest_inbox" if origin == "pasted_by_operator" else f"dj_reader_{publisher}"


def store_article(art: dict, *, root: Path | None = None) -> dict:
    """Write `<root>/<publisher>/<YYYY-MM-DD>/<sha>.json` (full text, local,
    gitignored) and one corpus row in `news_corpus/<registry id>/<date>.jsonl`
    (metadata + a 280-char lead). Idempotent by `sha`: a second store of the
    same text writes nothing and returns `duplicate: True`."""
    root = Path(root) if root else corpus_root()
    # One writer at a time (2026-09-27): reader WORKER processes share this
    # corpus; the existence check, the write and the corpus-row append are one
    # step, so two workers storing the same text write it once.
    with DG.file_lock(root / "_store.lock"):
        return _store_article(art, root)


def _store_article(art: dict, root: Path) -> dict:
    from backend.services import dowjones_claims as DC
    from backend.services import news_registry as NR
    pub = art.get("publisher") or DC.publisher_of(art.get("url", ""), art.get("text", "")) or "dowjones"
    sha = art.get("sha") or DC.text_sha(art.get("text", ""))
    seen = art.get("first_seen_utc") or DC.now_iso()
    day = seen[:10]
    existing = list(root.glob(f"*/*/{sha}.json"))
    if existing:
        return {"path": str(existing[0]), "sha": sha, "duplicate": True}
    origin = art.get("origin") or "web_reader"
    rec = {"sha": sha, "publisher": pub, "url": art.get("url"), "title": art.get("title"),
           "byline": art.get("byline"), "published_utc": art.get("published_utc"),
           "first_seen_utc": seen, "chars": len(art.get("text") or ""),
           "column": art.get("column"), "origin": origin,
           "licence": art.get("licence") or LICENCE,
           "text": art.get("text") or ""}
    # 2026-09-29: an article whose own dateline is more than
    # READER_MAX_ARTICLE_AGE_DAYS before we read it is ARCHIVE (455 of 995 Dow
    # Jones pages in 36 h were, median 65 days old); undated is not archive
    try:
        _pt = datetime.fromisoformat(str(rec["published_utc"])) if rec["published_utc"] else None
        _st = datetime.fromisoformat(str(seen))
        if _pt is not None and _pt.tzinfo is None:
            _pt = _pt.replace(tzinfo=timezone.utc)
        if _st.tzinfo is None:
            _st = _st.replace(tzinfo=timezone.utc)
        rec["archive"] = bool(_pt is not None and (_st - _pt).total_seconds() >
                              float(_cfg("READER_MAX_ARTICLE_AGE_DAYS", 4.0)) * 86400)
    except (TypeError, ValueError):
        rec["archive"] = False
    rec["pit_grade"] = NR.effective_pit_grade(
        {"published_utc": rec["published_utc"], "first_seen_utc": seen,
         "pit_grade": "first_seen_only"})
    # 2026-09-28 (the reader pool): HOW the page was reached (lane, section,
    # parent url, position on that page, depth) so grading can ask whether
    # prominence carries information; the MEDIA it carries (video / audio /
    # charts / images, titles and captions -- text only) and table rows; the
    # tickers it names.
    # 2026-09-29 (the browse lane): every page record carries what a digest
    # needs -- host, section, page class, the outbound links, the source kind.
    for k in ("tab", "profile", "attached_to", "read_s", "reached_by", "media", "tables",
              "tickers_named", "page_kind", "page_class", "host", "section",
              "outbound_links", "source_kind"):
        if k in art:
            rec[k] = art[k]
    p = root / pub / day / f"{sha}.json"
    DG.atomic_write_json(p, rec)
    if art.get("source_kind") == "general_news" or art.get("page_kind") == "front":
        # not a Dow Jones row: the registry's dj_reader_* sources stay Dow Jones
        # only; the record above is where the digest reads it
        return {"path": str(p), "sha": sha, "duplicate": False, "registry_id": None,
                "pit_grade": rec["pit_grade"]}

    sid = registry_source_id(pub, origin)
    row = {"source": sid, "first_seen_utc": seen, "published_utc": rec["published_utc"] or "",
           "tz_source": "America/New_York", "url": rec["url"] or "",
           "title": rec["title"] or "", "body": (rec["text"] or "")[:280], "lang": "en",
           "tickers": list(art.get("tickers") or []), "entity_tags": [f"column:{rec['column']}"],
           "raw_id": sha, "pit_grade": rec["pit_grade"], "fetcher": origin,
           "licence": LICENCE}
    cdir = Path(_config.OPTIMUS_LEDGER_DIR) / "news_corpus" / sid
    cdir.mkdir(parents=True, exist_ok=True)
    with (cdir / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"path": str(p), "sha": sha, "duplicate": False, "registry_id": sid,
            "pit_grade": rec["pit_grade"]}


# ──────────────────────── tab discipline (2026-09-27) ────────────────────────

BLANK_URL = "about:blank"


def max_pages_per_tab() -> int:
    return int(_cfg("WEB_READER_MAX_PAGES_PER_TAB", 10))


def direct_open_ok(driver: Any, profile: str) -> bool:
    """True when `profile` is a DEDICATED instance and the driver can open a tab
    there directly (`open_tab`, under the instance proof) -- 2026-09-28.

    `window.open` from a parent tab (`open_from_tab`) existed only because the
    old attach reached every profile of Murat's main Chrome, so a new tab had
    to inherit the profile of a tab he opened by hand. On the dedicated Chrome
    a fresh profile's pop-up blocker refuses a `window.open` without a user
    gesture: 0 new tabs on every lane on 2026-09-28. The dedicated instance
    opens directly; `open_from_tab` stays for any other operator profile."""
    ded = getattr(driver, "dedicated_profiles", None)
    try:
        is_ded = callable(ded) and profile in ded()
    except Exception:  # noqa: BLE001 -- unknown means not dedicated
        is_ded = False
    return bool(is_ded) and callable(getattr(driver, "open_tab", None))


def open_lane_tab(driver: Any, profile: str, url: str, *, parent: str | None = None,
                  throttle: Throttle | None = None, host: str = "",
                  what: str = "open_tab", take_slot: bool = True) -> dict:
    """Open ONE new tab at `url` for a reader lane; the open IS a page load.

    * dedicated profile -> `driver.open_tab` (URL rules, instance proof, the
      landed-host check: all inside the client); no parent tab is used;
    * any other operator profile -> `driver.open_from_tab(parent, ...)`, which
      needs a parent (none -> REFUSED_NO_PARENT_TAB).

    The throttle slot is taken first (pacing is served before the request)
    and GIVEN BACK when the open fails without producing a tab, so a failed
    open never counts against the hourly or daily caps. If the client did
    record a new tab before refusing (landed off-host), the slot stands (a
    page did load) and that tab -- ours -- is closed here, best effort.
    Returns the driver's dict with `how` ("direct_open" / the diff method)
    and `label` filled in."""
    direct = direct_open_ok(driver, profile)
    if not direct and not parent:
        raise ReaderRefused(f"REFUSED_NO_PARENT_TAB: {profile!r} is not a dedicated instance, "
                            f"so a new tab needs a parent tab to open from")
    if throttle is not None and take_slot:
        throttle.acquire(what, host=host)
    reg = getattr(driver, "_OPENED_TABS", None)
    before = set(reg) if isinstance(reg, (set, frozenset)) else None
    try:
        if direct:
            op = dict(driver.open_tab(url, profile_name=profile))
            op.setdefault("how", "direct_open")
        else:
            op = dict(driver.open_from_tab(parent, url, profile_name=profile))
    except BaseException as exc:
        reg2 = getattr(driver, "_OPENED_TABS", None)
        made = (set(reg2) - before) if (before is not None and isinstance(
            reg2, (set, frozenset))) else set()
        for h in sorted(made):                   # a tab WE opened that was refused after
            try:
                driver.browser("close", profile_name=profile, target_id=h)
            except Exception:  # noqa: BLE001 -- best effort; accounted as an orphan
                pass
        try:
            exc.tab_made = bool(made)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 -- a builtin that takes no attributes
            pass
        if throttle is not None and take_slot and not made:
            throttle.refund(f"open failed before any page load: {type(exc).__name__}: "
                            f"{str(exc)[:100]}")
        raise
    op.setdefault("label", op.get("new_tab"))
    op["direct"] = direct
    return op


def own_blank_tab_verb(driver: Any, profile: str, tab: str, verb: str,
                       url: str | None = None) -> dict:
    """`blank`, or `navigate`/`close` on a blanked tab THIS process opened.

    A thin call to `openclaw_client.own_blank_tab` (2026-09-27): the guard that
    knows its own blank tabs lives in the client now, so this module holds no
    second copy of the rule. A refusal comes back as `ReaderRefused` with the
    client's reason in front (`REFUSED_NOT_OUR_TAB`, ...). A driver without
    `own_blank_tab` (a test stub) gets the plain verb."""
    fn = getattr(driver, "own_blank_tab", None)
    if not callable(fn):
        if verb == "blank":
            return driver.browser("navigate", BLANK_URL, profile_name=profile, target_id=tab)
        args = (url,) if verb == "navigate" else ()
        return driver.browser(verb, *args, profile_name=profile, target_id=tab)
    try:
        return fn(verb, tab, url, profile_name=profile)
    except Exception as exc:
        if type(exc).__name__ == "OpenClawRefused":
            raise ReaderRefused(str(exc)) from exc
        raise


#: A raw CDP target id (the attach profile, 2026-09-28): 128 random bits, unique
#: to one tab of one browser, never reissued -- as safe across runs as a
#: session-qualified chrome-mcp handle.
CDP_TARGET_ID = re.compile(r"^[0-9A-F]{32}$")


def is_stable_handle(h: str) -> bool:
    parts = str(h or "").split(":")
    return (len(parts) == 3 and parts[0] == "chrome-mcp") or bool(CDP_TARGET_ID.match(str(h or "")))


def close_leftover_tabs(driver: Any, profile: str, handles: Any, *,
                        log: dict | None = None) -> dict:
    """Close tabs an EARLIER run recorded as opened and never closed.

    Only a handle that (1) is session-qualified (`chrome-mcp:<nonce>:<n>` --
    a bare `tN` is reissued and may name one of Murat's own tabs now), (2) is
    in the CURRENT listing, and (3) is on a Dow Jones host. Such a tab is
    adopted into `_OPENED_TABS` (the receipt is the proof it was ours) and
    closed with the guarded verb. Returns `{candidates, closed, skipped}`."""
    out = log if log is not None else {}
    handles = sorted({str(h) for h in (handles or []) if h})
    out.update({"candidates": handles, "closed": [], "skipped": {}})
    if not handles:
        return out
    try:
        inv = getattr(driver, "invalidate_tabs_cache", None)
        if callable(inv):
            inv(profile)
        listing = driver.tabs(profile_name=profile)
    except Exception as exc:  # noqa: BLE001 -- a cleanup that cannot list says so
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return out
    by_handle = {str(t.get("targetId") or t.get("tabId") or ""): t for t in listing}
    opened = getattr(driver, "_OPENED_TABS", None)
    for h in handles:
        if not is_stable_handle(h):
            out["skipped"][h] = "not session-qualified (a tN alias is reissued)"
            continue
        t = by_handle.get(h)
        if t is None:
            out["skipped"][h] = "not present"
            continue
        u = str(t.get("url") or "")
        # 2026-09-28: on the DEDICATED instance a raw CDP target id is unique to
        # that Chrome, so a leftover our receipt names that sits on about:blank
        # (a crashed run's blanked lane tab) is ours too -- these were the blank
        # tabs piling up in the MuratClaw window. Elsewhere a blank tab could be
        # the owner's, so it is still skipped.
        blank_ours = u == BLANK_URL and direct_open_ok(driver, profile)
        if not host_ok(u) and not blank_ours:
            out["skipped"][h] = f"not on a Dow Jones host ({u[:60]!r})"
            continue
        if opened is not None:
            opened.add(h)
        try:
            r = driver.browser("close", profile_name=profile, target_id=h)
            if r.get("rc") == 0:
                out["closed"].append(h)
            else:
                out["skipped"][h] = f"close rc {r.get('rc')}"
        except Exception as exc:  # noqa: BLE001
            out["skipped"][h] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return out


# ─────────────────────── search / quote-page link choice ─────────────────────

#: "3 hours ago", "2 days ago", "1 wk ago"
REL_AGE_RE = re.compile(r"\b(\d{1,3})\s*(min|mins|minute|minutes|h|hr|hrs|hour|hours|"
                        r"d|day|days|wk|wks|week|weeks)\s+ago\b", re.I)
NUM_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b")
#: Sponsored / advertising units that carry an article-shaped link.
AD_TEXT = re.compile(r"sponsored|advertis|paid\s+(program|post|content)|partner\s+content|"
                     r"presented\s+by|promoted|buyside", re.I)


def visible_date(text: str, now: datetime) -> datetime | None:
    """The first date a reader could SEE in `text`: a dateline
    (`Sept. 24, 2026`), a numeric `9/24/26`, or a relative age (`3 hours
    ago`). None when nothing dated is visible."""
    iso = parse_published(text or "")
    if iso:
        return datetime.fromisoformat(iso)
    m = NUM_DATE_RE.search(text or "")
    if m:
        mo, dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        yy = yy + 2000 if yy < 100 else yy
        try:
            return datetime(yy, mo, dd, tzinfo=timezone.utc)
        except ValueError:
            pass
    m = REL_AGE_RE.search(text or "")
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        if unit.startswith("min"):
            return now - timedelta(minutes=n)
        if unit.startswith("h"):
            return now - timedelta(hours=n)
        if unit.startswith("d"):
            return now - timedelta(days=n)
        return now - timedelta(weeks=n)
    return None


def select_search_links(snapshot_text: str, link_pattern: str, *, now: datetime,
                        max_age_days: int = 30, limit: int = 3) -> dict:
    """Article links from a company's quote/search page SNAPSHOT: the links
    `select_links` accepts (host, pattern, >= 12 chars, no account/money text
    by the narrower `ARTICLE_DENY_LINK_TEXT`), minus sponsored units, minus any whose visible date (in the link text or
    the tree lines under it, up to the next link) is older than
    `max_age_days`; at most `limit`, in page order. An undated link is kept
    (`published_visible: None`). Returns `{links, candidates, skipped_old,
    skipped_ad}`."""
    cands = select_links(snapshot_text, link_pattern, deny_text=ARTICLE_DENY_LINK_TEXT)
    tree = (snapshot_text or "").split("\nLinks:", 1)[0].splitlines()
    link_lines = []
    for i, ln in enumerate(tree):
        m = _SNAP_NODE.match(ln)
        if m and m.group(1).lower() == "link":
            link_lines.append((i, m.group(2).replace('\\"', '"').strip()))
    used: set[int] = set()

    def context(text: str) -> str:
        for k, (i, name) in enumerate(link_lines):
            if name == text and i not in used:
                used.add(i)
                end = link_lines[k + 1][0] if k + 1 < len(link_lines) else len(tree)
                return "\n".join(tree[i:min(end, i + 7)])
        return text

    out: dict[str, Any] = {"links": [], "candidates": len(cands), "skipped_old": [],
                           "skipped_ad": []}
    for lk in cands:
        ctx = context(lk["text"])
        if AD_TEXT.search(ctx) or AD_TEXT.search(lk["url"]):
            out["skipped_ad"].append(lk["url"])
            continue
        when = visible_date(ctx, now)
        if when is not None and (now - when) > timedelta(days=max_age_days):
            out["skipped_old"].append(lk["url"])
            continue
        out["links"].append(dict(lk, published_visible=when.isoformat(timespec="seconds")
                                 if when else None))
        if len(out["links"]) >= limit:
            break
    return out


# ─────────────────────────────── the reader ─────────────────────────────────

@dataclass
class Reader:
    """One reading session in one lane tab this process opened.

    `driver` is `openclaw_client` (or a stub in tests). Every page load goes
    through `throttle.acquire`. `max_pages` is the session cap.

    Tab discipline (2026-09-27): after each read the tab is blanked
    (`blank_after_read`); with a `parent`, a tab that has served
    `max_tab_pages` page loads is closed and re-opened from it on the next
    load. `opened` lists every handle this Reader held, `closed` what closing
    each one returned; `orphans()` is the difference."""

    profile: str
    tab: str
    throttle: Throttle
    driver: Any = None
    max_pages: int = 20
    pages: int = 0
    log: list[dict] = field(default_factory=list)
    last_snapshot: str = ""
    wait_ms: int = 3500
    scroll_steps: tuple[int, int] = (2, 3)
    scrolled_reads: int = 0
    reads: int = 0
    lock: bool = True
    parent: str | None = None
    #: 2026-09-28: a dedicated instance re-opens a rotated tab with `open_tab`
    #: (no parent tab); see `open_lane_tab`.
    direct_open: bool = False
    max_tab_pages: int = field(default_factory=max_pages_per_tab)
    tab_pages: int = 0
    blank_after_read: bool = True
    #: 2026-09-28 (Murat: "opens a website then it goes blank, but if it clicks
    #: go back ... they launch back"): on a dedicated instance (`direct_open`)
    #: the tab is CLOSED after its read instead of navigated to about:blank,
    #: and the next page load opens a fresh tab AT its URL. No blank page is
    #: ever shown, no history entry is left behind, and a blank tab never has
    #: to be told apart from another worker's. None -> follow `direct_open`.
    close_after_read: bool | None = None
    retired: bool = False
    closes_after_read: int = 0
    #: throttle line of this Reader's last page load (a BLANK page gives it back)
    _slot_line: str | None = None
    slot_refunds: list[str] = field(default_factory=list)
    blanked: bool = False
    blanks: int = 0
    blank_failures: list[str] = field(default_factory=list)
    needs_reopen: bool = False
    opened: list[str] = field(default_factory=list)
    closed: dict[str, bool] = field(default_factory=dict)
    close_errors: dict[str, str] = field(default_factory=dict)
    rotations: list[dict] = field(default_factory=list)
    #: host -> {page class -> count} for every page this Reader classified
    page_classes: dict = field(default_factory=dict)
    #: labels carried onto `page_log.jsonl` lines
    lane: str | None = None
    worker: str | None = None
    #: write `page_log.jsonl` lines (the runs set it; a bare Reader in a test does not)
    page_log: bool = False
    #: Local sleeps (the settle after a load, the pauses between scroll steps).
    #: None -> the throttle's `sleep_fn`, so a test's fake clock drives them.
    sleep_fn: Callable[[float], None] | None = None
    #: The throttle clock's time of the last page load on this tab, until the
    #: settle has been served (`settle()`).
    loaded_at: datetime | None = None
    settles: list[float] = field(default_factory=list)
    _scroll_plan: list[int] | None = None
    _lock_path: Path | None = None
    _cli0: dict | None = None

    def __post_init__(self) -> None:
        if self.driver is None:
            from backend.services import openclaw_client as OC
            self.driver = OC
        if self.lock:
            self._lock_path = acquire_reader_lock()
        if self.tab and self.tab not in self.opened:
            self.opened.append(self.tab)
        self._cli0 = self.cli_ledger()

    def cli_ledger(self) -> dict | None:
        """The driver's CLI ledger now, or None for a driver without one."""
        led = getattr(self.driver, "cli_ledger", None)
        try:
            return led() if callable(led) else None
        except Exception:  # noqa: BLE001 -- a receipt field, never a failure
            return None

    def close(self, *, write_footprint: bool = True) -> dict | None:
        """Release the one-reader lock and write the session's footprint."""
        fp = None
        if write_footprint:
            now = self.cli_ledger()
            fp = footprint_receipt(self.log, scrolled=self.scrolled_reads, reads=self.reads,
                                   cli_now=now or {},
                                   cli_since=self._cli0 if now else None)
        if self._lock_path is not None:
            release_reader_lock(self._lock_path)
            self._lock_path = None
        return fp

    # ── tab discipline ──────────────────────────────────────────────────────

    def blank(self) -> bool:
        """Navigate the tab to `about:blank` so the page's renderer memory is
        dropped while the lane waits for its next turn. Not a page load (no
        request reaches a site), so no throttle. A failure is recorded, never
        raised: the article is already stored."""
        if self.retired:
            return False
        if self.direct_open and self.close_after_read is not False:
            return self.retire()
        if not self.blank_after_read or self.blanked or self.needs_reopen:
            return False
        try:
            r = own_blank_tab_verb(self.driver, self.profile, self.tab, "blank")
            if r.get("rc") not in (0, None):
                raise ReaderRefused(f"rc {r.get('rc')}: {(r.get('stderr') or '')[:120]}")
        except Exception as exc:  # noqa: BLE001 -- say it, never hide it
            self.blank_failures.append(f"{self.tab}: {type(exc).__name__}: {str(exc)[:160]}")
            return False
        self.blanked, self.last_snapshot, self.loaded_at = True, "", None
        self.blanks += 1
        return True

    def retire(self) -> bool:
        """Close the tab whose page has been read (dedicated instance only);
        the next `navigate` opens a fresh tab at its URL (`_reopen`). A close
        that fails is recorded in `close_errors` (the tab is an orphan on the
        receipt) and the lane still moves on to a fresh tab."""
        if self.retired or self.needs_reopen:
            return False
        self.close_tab()
        self.retired, self.last_snapshot, self.loaded_at = True, "", None
        self.closes_after_read += 1
        return True

    def refund_slot(self, why: str) -> bool:
        """Give back the throttle slot of this Reader's last page load (a
        BLANK or empty page loaded nothing worth a slot; Murat 2026-09-28)."""
        line, self._slot_line = self._slot_line, None
        if not line:
            return False
        try:
            ok = bool(self.throttle.refund(why, line=line))
        except TypeError:          # a test double without the `line` keyword
            return False
        except Exception:  # noqa: BLE001 -- a receipt detail, never a failure
            return False
        if ok:
            self.slot_refunds.append(str(why)[:120])
        return ok

    def close_tab(self) -> bool:
        """Close the CURRENT tab (a blanked one through `own_blank_tab_verb`);
        the result is recorded in `closed` / `close_errors`."""
        tab = self.tab
        if self.closed.get(tab):
            return True
        if self.needs_reopen:            # its handle is gone (session reset): nothing to close
            self.closed.setdefault(tab, False)
            self.close_errors.setdefault(tab, "LOST: handle reissued by a session reset")
            return False
        try:
            r = (own_blank_tab_verb(self.driver, self.profile, tab, "close") if self.blanked
                 else self.driver.browser("close", profile_name=self.profile, target_id=tab))
            ok = r.get("rc") == 0
            if not ok:
                self.close_errors[tab] = f"rc {r.get('rc')}: {(r.get('stderr') or '')[:160]}"
        except Exception as exc:  # noqa: BLE001 -- say it, never hide it
            ok = False
            self.close_errors[tab] = f"{type(exc).__name__}: {str(exc)[:200]}"
        self.closed[tab] = ok
        return ok

    def count_page(self, url: str, cls: str) -> None:
        """Count one classified page load (per host) and log it."""
        host = host_of(url) or "-"
        row = self.page_classes.setdefault(host, {})
        row[cls] = row.get(cls, 0) + 1
        if self.page_log:
            log_page(host, cls, url, lane=self.lane, worker=self.worker)

    def orphans(self) -> list[str]:
        return [h for h in self.opened if not self.closed.get(h)]

    def _reopen(self, url: str, why: str) -> None:
        """Close this tab and open a fresh one from `parent` AT `url` (that
        open is the page load)."""
        old = self.tab
        closed = self.close_tab()
        self._page("reopen", url)
        try:
            op = open_lane_tab(self.driver, self.profile, url, parent=self.parent,
                               throttle=self.throttle, take_slot=False)
        except BaseException as exc:
            # nothing loaded: give the slot `_page` took back, and the page count
            if not getattr(exc, "tab_made", False):
                self.throttle.refund(f"reopen failed: {type(exc).__name__}: {str(exc)[:100]}")
                self.pages -= 1
                self.log.pop()
            self.needs_reopen = True
            raise
        self.tab = op["new_tab"]
        self.opened.append(self.tab)
        self.tab_pages, self.blanked, self.needs_reopen, self.last_snapshot = 1, False, False, ""
        self.retired = False
        self.log[-1]["tab"] = self.tab
        self.rotations.append({"at": self.log[-1]["at"], "old": old, "old_closed": closed,
                               "new": self.tab, "why": why, "url": url})
        self._mark_loaded()

    # ── local time: the settle and the scroll pauses (2026-09-27) ───────────
    #
    # These were `browser wait --time N` CLI calls: a fresh node process
    # (~4-6 s of start-up measured with `browser --help`, ~9 s per call on the
    # night of 2026-09-27) plus a tab listing for the host check, to make the
    # gateway run `setTimeout(N)` OUTSIDE its Chrome MCP operation lock
    # (openclaw 2026.9.5 `waitForExistingSessionCondition`). A pure timer does
    # nothing to the page, so the same seconds now pass HERE: no browser
    # action is skipped and every ACTION keeps its host checks. And a settle
    # is served lazily -- only what is left of it when the tab is next
    # touched -- so the time another lane spends working counts toward it.

    def _sleep(self, s: float) -> None:
        if s > 0:
            (self.sleep_fn or self.throttle.sleep_fn)(s)

    def _mark_loaded(self) -> None:
        self.loaded_at = self.throttle.now_fn()

    def settle(self) -> float:
        """Serve what is left of the `wait_ms` settle since the last load on
        this tab; return the seconds slept (0 when other work covered it)."""
        if self.loaded_at is None:
            return 0.0
        elapsed = (self.throttle.now_fn() - self.loaded_at).total_seconds()
        rem = max(0.0, self.wait_ms / 1000.0 - elapsed)
        self.loaded_at = None
        self._sleep(rem)
        self.settles.append(round(rem, 2))
        return rem

    # ── page loads ──────────────────────────────────────────────────────────

    def scroll_through(self) -> int:
        """2-3 PageDown presses with jittered 1-3 s pauses -- a person reads
        down a page; an instant extraction with no scroll is the tell. The
        pauses are local (see above); each PRESS is a guarded browser action
        with its host check before and its result checked after."""
        self.settle()
        plan, self._scroll_plan = (self._scroll_plan or self.plan_scroll()), None
        done = 0
        for pause_ms in plan:
            self._sleep(pause_ms / 1000.0)
            r = self.driver.browser("press", "PageDown", profile_name=self.profile,
                                    target_id=self.tab)
            self._check_still_on_host(r)
            done += 1
        return done

    def plan_scroll(self) -> list[int]:
        """The scroll for one read: 2-3 steps, each after a 1-3 s pause (ms),
        drawn from the throttle's generator. `load_article` draws it right
        after the load, so an interleaved rotation consumes the generator in
        the same order a serial one does (the draws that set the throttle
        gaps are the same draws)."""
        rng = self.throttle._rng
        n = int(rng.integers(self.scroll_steps[0], self.scroll_steps[1] + 1))
        return [int(rng.uniform(1000, 3000)) for _ in range(n)]

    def _page(self, what: str, url: str | None) -> float:
        if self.pages >= self.max_pages:
            raise ReaderRefused(f"REFUSED_SESSION_CAP: {self.pages} pages >= {self.max_pages}")
        if url is not None and not host_ok(url):
            raise ReaderRefused(f"REFUSED_HOST: {url!r} is not on {hosts()}")
        host = (urlsplit(url or "").hostname or "").lower().removeprefix("www.") if url else ""
        waited = self.throttle.acquire(what, host=host)
        self._slot_line = getattr(self.throttle, "_last_line", None)
        self.pages += 1
        self.log.append({"page": self.pages, "what": what, "url": url, "waited_s": waited,
                         "at": self.throttle.now_fn().isoformat(timespec="seconds")})
        return waited

    def _check_still_on_host(self, r: dict) -> None:
        if r.get("left_allowed_hosts"):
            raise ReaderRefused(f"REFUSED_LEFT_HOSTS: the tab is now on {r.get('tab_url_after')!r}")
        if r.get("rc") not in (0, None):
            raise ReaderRefused(f"REFUSED_VERB_FAILED: {r.get('verb')} rc {r.get('rc')}: "
                                f"{(r.get('stderr') or '')[:160]}")

    def navigate(self, url: str) -> None:
        if (self.parent or self.direct_open) and (self.needs_reopen or self.retired or
                                                  self.tab_pages >= self.max_tab_pages):
            self._reopen(url, "lost_on_reattach" if self.needs_reopen else
                         "fresh_tab_per_page" if self.retired else
                         f"served {self.tab_pages} pages >= {self.max_tab_pages}")
            return
        self._page("navigate", url)
        if self.blanked:
            r = own_blank_tab_verb(self.driver, self.profile, self.tab, "navigate", url)
        else:
            r = self.driver.browser("navigate", url, profile_name=self.profile,
                                    target_id=self.tab)
        self.blanked = False
        self.tab_pages += 1
        self._check_still_on_host(r)
        self._mark_loaded()

    def snapshot(self) -> str:
        self.settle()
        r = self.driver.browser("snapshot", "--format", "ai", "--urls", "--limit", "900",
                                profile_name=self.profile, target_id=self.tab)
        self.last_snapshot = r.get("stdout") or ""
        n_full = len(parse_snapshot(self.last_snapshot)["links"])
        cut = int(_cfg("WEB_READER_SNAPSHOT_CUT_CHARS", 38000))
        if self.last_snapshot.strip() and (n_full == 0 or len(self.last_snapshot) >= cut):
            # 2026-09-28: the CLI cuts a snapshot at ~40,000 chars and the
            # `Links:` appendix is LAST, so a big page (every WSJ / Barron's
            # stock page: 51 of 51 returned 0 links) loses its URLs. The
            # interactive-only tree is small enough to keep them. A CUT page
            # can still show a few inline nav links (the Barron's PLTR page:
            # 38 nav links, 0 of its 37 article links), so a snapshot at the
            # cut length is re-read too, and the interactive one is used when
            # it carries MORE links.
            r2 = self.driver.browser("snapshot", "--format", "ai", "--urls", "--interactive",
                                     "--compact", "--limit", "2500",
                                     profile_name=self.profile, target_id=self.tab)
            if len(parse_snapshot(r2.get("stdout") or "")["links"]) > n_full:
                self.last_snapshot = r2.get("stdout") or ""
                self.snapshot_fallbacks = getattr(self, "snapshot_fallbacks", 0) + 1
        return self.last_snapshot

    def snapshot_after_scroll(self, pages: int = 4, pause_s: float = 1.2) -> str:
        """Scroll `pages` screens first (a stock page loads its news list
        lazily), then `snapshot()`. The presses go through the same guarded
        driver call as every other action on this tab."""
        self.settle()
        for _ in range(max(0, int(pages))):
            self.driver.browser("press", "PageDown", profile_name=self.profile,
                                target_id=self.tab)
            (self.sleep_fn or self.throttle.sleep_fn)(pause_s)
        return self.snapshot()

    def read_listing(self, url: str, link_pattern: str, *, text_pattern: str | None = None,
                     limit: int | None = None) -> list[dict]:
        """navigate -> wait -> snapshot -> links chosen FROM the snapshot."""
        self.navigate(url)
        return select_links(self.snapshot(), link_pattern, text_pattern=text_pattern,
                            limit=limit)

    def read_article(self, link: dict | str, *, column: str | None = None,
                     origin: str = "web_reader", store: bool = True,
                     tickers: list[str] | None = None) -> dict:
        """click the link's ref (when the last snapshot shows it as a link) or
        navigate to its URL -> settle -> fixed innerText read -> clean -> store
        -> blank the tab. `load_article` + `finish_article`; a rotation that
        interleaves lanes calls the two halves separately."""
        t0 = time.time()
        self.load_article(link)
        return self.finish_article(link, column=column, origin=origin, store=store,
                                   tickers=tickers, t0=t0)

    def _read_media(self) -> tuple[dict | None, list[dict]]:
        """(the `read_media` reply, its related links) for the current tab; a
        failure is recorded on the reader and returns (None, [])."""
        try:
            got = self.driver.read_media(self.tab, profile_name=self.profile)
        except Exception as exc:  # noqa: BLE001 -- the article stands without it
            self.media_errors = getattr(self, "media_errors", []) + [
                f"{type(exc).__name__}: {str(exc)[:120]}"]
            return None, []
        if got.get("error"):
            self.media_errors = getattr(self, "media_errors", []) + [str(got["error"])[:120]]
            return None, []
        rel = [r for r in (got.get("related_links") or []) if isinstance(r, dict)]
        return got, rel

    def load_article(self, link: dict | str) -> None:
        """The PAGE LOAD half: throttle slot, then click the snapshot ref or
        navigate, with the host checks before and after. No settle here."""
        url = link if isinstance(link, str) else link.get("url")
        ref = None if isinstance(link, str) else link.get("ref")
        if (ref and self.last_snapshot and not self.blanked and not self.retired
                and ref_is_clickable(self.last_snapshot, ref)):
            self._page("click", url)
            r = self.driver.browser("click", ref, profile_name=self.profile, target_id=self.tab)
            self.tab_pages += 1
            self._check_still_on_host(r)
            self._mark_loaded()
        else:
            self.navigate(url)
        self._scroll_plan = self.plan_scroll()

    def finish_article(self, link: dict | str, *, column: str | None = None,
                       origin: str = "web_reader", store: bool = True,
                       tickers: list[str] | None = None, t0: float | None = None,
                       extra: dict | None = None, with_media: bool = False,
                       universe: set[str] | frozenset[str] | None = None) -> dict:
        """The READ half, on the page `load_article` loaded: what is left of
        the settle, 2-3 scroll steps, the fixed innerText read, clean, store,
        blank. No page load.

        The reader pool (2026-09-28) adds three optional things, all off by
        default: `extra` fields stored with the record (`reached_by`,
        `page_kind`); `with_media` -- a second FIXED read (`read_media`) for the
        media the page carries, its table rows and its "related" links (the
        links come back as `art["_related"]`, never stored); `universe` -- the
        tickers the text names (`tickers_named`)."""
        from backend.services import dowjones_claims as DC
        url = link if isinstance(link, str) else link.get("url")
        t0 = time.time() if t0 is None else t0
        steps = self.scroll_through()
        self.reads += 1
        self.scrolled_reads += bool(steps)
        got = self.driver.read_text(self.tab, profile_name=self.profile)
        if got.get("error") or not (got.get("text") or "").strip():
            # An empty read is a FAILURE with a name, never a page with no text.
            self.count_page(got.get("url") or url, "BLANK")
            self.refund_slot(f"empty read: {url}")
            self.last_snapshot = ""
            self.blank()
            raise ReaderRefused(f"REFUSED_EMPTY_READ: {url!r}: "
                                f"{(got.get('error') or 'no text returned')[:200]}")
        final_url = got.get("url") or url
        raw = got.get("text") or ""
        title = got.get("title") or (None if isinstance(link, str) else link.get("text"))
        text = clean_text(raw, title)
        # 2026-09-28: every load is CLASSIFIED; only OK is stored as an article
        cls = classify_page(url=url, final_url=final_url, title=title, raw=raw, text=text)
        self.count_page(final_url, cls)
        if cls == "REDIRECTED_OFF_HOST":
            raise ReaderRefused(f"REFUSED_LEFT_HOSTS: read landed on {final_url!r}")
        if cls != "OK":
            if cls == "BLANK":
                self.refund_slot(f"BLANK page: {final_url}")
            self.last_snapshot = ""
            self.blank()
            if cls == "CHALLENGE":
                raise ReaderRefused(f"REFUSED_CHALLENGE: {final_url!r} shows a bot check or "
                                    f"block page; this lane stops (nothing is done to pass it)")
            raise ReaderRefused(f"PAGE_{cls}: {final_url!r} ({len(text)} chars) not stored")
        pub = DC.publisher_of(final_url, text)
        art = {"url": final_url, "title": title, "byline": parse_byline(text),
               "page_class": cls,
               "published_utc": parse_published(text), "text": text,
               "first_seen_utc": DC.now_iso(), "chars": len(text), "raw_chars": len(raw),
               "publisher": pub, "origin": origin, "tab": self.tab, "profile": self.profile,
               "attached_to": got.get("attached_to"),
               "paywall_suspected": bool(re.search(r"subscribe to continue|to keep reading|"
                                                   r"choose your .* subscription", raw, re.I)),
               "column": column or DC.column_of(final_url, title or "", text, pub)}
        if tickers:
            art["tickers"] = list(tickers)
        if universe:
            art["tickers_named"] = names_tickers(text, universe)
        if extra:
            art.update(extra)
        if with_media and callable(getattr(self.driver, "read_media", None)):
            art["_media_raw"], art["_related"] = self._read_media()
            if art["_media_raw"] is not None:
                from backend.services import media_transcripts as MT
                art["media"] = MT.summarize(art["_media_raw"].get("media"))
                art["tables"] = [t for t in (art["_media_raw"].get("tables") or [])
                                 if isinstance(t, dict) and t.get("rows")][:5]
        art["sha"] = DC.text_sha(text)
        art["scroll_steps"] = steps
        art["read_s"] = round(time.time() - t0, 2)
        if store and text:
            art["stored"] = store_article(art)
        self.last_snapshot = ""
        self.blank()
        return art


# ───────────── every page load is CLASSIFIED before it is stored ─────────────
#
# Murat, 2026-09-28 17:00: "its making issues at times and opening blanks or 404
# pages". Only an OK page is stored as an article; every other class is counted
# per host on the receipt and in `page_log.jsonl`. A CHALLENGE (a bot check or
# block page) stops that lane: nothing is done to get around it.

PAGE_CLASSES = ("OK", "BLANK", "NOT_FOUND", "PAYWALL_STUB", "SIGNED_OUT", "CHALLENGE",
                "REDIRECTED_OFF_HOST")
#: visible text below this many characters is a BLANK page
PAGE_MIN_CHARS = 200
_NOT_FOUND = re.compile(
    r"\b(page not found|404 error|error 404|404 not found|we can(?:'|no)t find (?:the|that) page|"
    r"page (?:you are|you're) looking for (?:does not|doesn't|cannot|can't|could not)|"
    r"this page (?:is|has been) (?:no longer available|removed)|symbol not found|"
    r"no (?:results|matches) (?:found )?for)\b", re.I)
_CHALLENGE = re.compile(
    r"(captcha|verify (?:that )?you are (?:a )?human|are you a robot|press (?:&|and) hold|"
    r"unusual (?:traffic|activity) from your|access (?:to this page has been )?denied|"
    r"request (?:was |has been )?blocked|please enable (?:js|javascript) and disable any ad blocker|"
    r"checking your browser)", re.I)
_PAYWALL = re.compile(r"(subscribe to continue|to keep reading|continue reading your article with|"
                      r"choose your .{0,40}subscription|this article is for subscribers|"
                      r"already a subscriber\??\s*sign in)", re.I)
_SIGN_IN = re.compile(r"\bsign in\b", re.I)
_PAYWALL_TITLE = re.compile(r"^\s*(subscribe to (read|continue)|subscriber only|subscribe now)\b",
                            re.I)
#: a paywalled page shorter than this is a stub, not an article
PAYWALL_STUB_MAX_CHARS = 2500


def classify_page(*, url: str, final_url: str | None, title: str | None, raw: str,
                  text: str | None = None, hosts_allowed: Callable[[str], bool] | None = None
                  ) -> str:
    """PURE. One of PAGE_CLASSES for a page that was loaded and read.

    Order: off-host > blank > challenge > not found > signed out / paywall stub >
    OK. The heads (title + first 1,500 chars) carry the templates; a long
    article that merely MENTIONS "404" in its body is not NOT_FOUND."""
    fu = final_url or url or ""
    ok_host = hosts_allowed or host_ok
    if fu and fu != BLANK_URL and not fu.startswith("about:") and not ok_host(fu):
        return "REDIRECTED_OFF_HOST"
    body = (text if text is not None else raw) or ""
    if fu.startswith("about:") or len(body.strip()) < PAGE_MIN_CHARS:
        return "BLANK"
    head = f"{title or ''}\n{(raw or '')[:1500]}"
    if _CHALLENGE.search(head) and len(body) < 4000:
        return "CHALLENGE"
    if _NOT_FOUND.search(head) and len(body) < 6000:
        return "NOT_FOUND"
    if _PAYWALL.search(raw or "") and len(body) < PAYWALL_STUB_MAX_CHARS:
        return "SIGNED_OUT" if _SIGN_IN.search((raw or "")[:600]) else "PAYWALL_STUB"
    # 2026-09-29: a page whose TITLE is the paywall (FT: "Subscribe to read") is
    # a stub whatever its length (its offer text runs past the stub limit)
    if _PAYWALL_TITLE.search(title or ""):
        return "PAYWALL_STUB"
    return "OK"


def snapshot_title(snapshot_text: str) -> str:
    """The page title from an ai snapshot's `RootWebArea "..."` line ('' if none)."""
    m = re.search(r'RootWebArea "([^"]*)"', snapshot_text or "")
    return m.group(1) if m else ""


def page_log_path() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "dowjones" / "page_log.jsonl"


def log_page(host: str, cls: str, url: str, *, lane: str | None = None,
             worker: str | None = None, path: Path | None = None) -> None:
    """One line per classified page load (the status file and the receipts read it)."""
    try:
        DG.locked_append_line(path or page_log_path(), json.dumps(
            {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "host": host,
             "class": cls, "url": (url or "")[:300], "lane": lane, "worker": worker}))
    except Exception:  # noqa: BLE001 -- a log line never fails a read
        pass


# ─────────────── LANE O rotation: the host that is free soonest ──────────────
#
# Murat, 2026-09-28: "dont read it too slow, while its waiting make it read other
# pages then". The same-host floor (`Throttle.min_same_host_gap_s`, 18 s with the
# current pace) is what a single-host lane waits on; with more hosts in the
# rotation, the next load should go to the lane whose host has been idle longest
# -- then the floor binds less and the shared DRAWN gap is what paces the run.

def host_of(url: str) -> str:
    return (urlsplit(url or "").hostname or "").lower().removeprefix("www.")


def pick_next_lane(lanes: list[tuple[str, str]], last_load: dict[str, datetime],
                   now: datetime, same_host_gap_s: float) -> str | None:
    """PURE. `lanes` = [(lane_id, host)] in the caller's fair order. Returns the
    lane whose host is free SOONEST (`last_load[host] + same_host_gap_s`; a host
    never loaded is free now); ties keep the caller's order. None for no lanes."""
    best, best_at = None, None
    for lane, host in lanes:
        t = last_load.get(host)
        free_at = now if t is None else max(now, t + timedelta(seconds=same_host_gap_s))
        if best_at is None or free_at < best_at:
            best, best_at = lane, free_at
    return best


def host_aware_order(queues: dict[str, list], lane_host: dict[str, str], *,
                     same_host_gap_s: float, load_s: float, start: datetime,
                     last_load: dict[str, datetime] | None = None) -> list[tuple[str, Any]]:
    """PURE simulation of the rotation `pick_next_lane` produces: each load
    takes `load_s`; returns [(lane, item)] in load order. Lanes keep their own
    item order; an exhausted lane drops out."""
    qs = {k: list(v) for k, v in queues.items() if v}
    seen = dict(last_load or {})
    now = start
    out: list[tuple[str, Any]] = []
    order = list(qs)
    while qs:
        live = [(k, lane_host.get(k, k)) for k in order if k in qs]
        k = pick_next_lane(live, seen, now, same_host_gap_s)
        h = lane_host.get(k, k)
        t = seen.get(h)
        if t is not None:
            now = max(now, t + timedelta(seconds=same_host_gap_s))
        out.append((k, qs[k].pop(0)))
        seen[h] = now
        now = now + timedelta(seconds=load_s)
        if not qs[k]:
            del qs[k]
        order.remove(k)
        order.append(k)
    return out


# ─────────────────── LANE O5: the yield check on every run ───────────────────
#
# 2026-09-28 01:34-02:17: 51 of 51 WSJ / Barron's stock pages returned
# `links_on_page: 0` for hours and nothing noticed -- page LOADS were counted,
# page YIELD was not (handoff §5 R3). After the first N pages of a run (config
# `READER_YIELD_CHECK_AFTER`, 10) and at the end, the run prints and records
# links per page and characters per page per lane, and a lane that is ZERO on
# EVERY page it has loaded refuses by name.

@dataclass
class YieldCheck:
    after: int = field(default_factory=lambda: int(_cfg("READER_YIELD_CHECK_AFTER", 10)))
    min_pages_per_lane: int = 2
    rows: list[dict] = field(default_factory=list)
    reports: list[dict] = field(default_factory=list)
    printer: Callable[[str], None] | None = print

    def record(self, lane: str, *, links: int | None = None, chars: int | None = None,
               kind: str = "page") -> dict | None:
        """One page's yield. Returns the report when this record triggers one
        (the Nth page); raises `ReaderRefused` from that report when a lane is
        zero on every page."""
        self.rows.append({"lane": lane, "links": links, "chars": chars, "kind": kind})
        if len(self.rows) == self.after:
            return self.check("after_first_pages")
        return None

    def report(self, when: str) -> dict:
        lanes: dict[str, dict] = {}
        for r in self.rows:
            d = lanes.setdefault(r["lane"], {"pages": 0, "links": [], "chars": []})
            d["pages"] += 1
            if r["links"] is not None:
                d["links"].append(int(r["links"]))
            if r["chars"] is not None:
                d["chars"].append(int(r["chars"]))
        out = {"when": when, "pages": len(self.rows), "lanes": {}}
        zero = []
        for lane, d in lanes.items():
            lk, ch = d["links"], d["chars"]
            row = {"pages": d["pages"],
                   "links_per_page": round(sum(lk) / len(lk), 1) if lk else None,
                   "zero_link_pages": sum(1 for x in lk if x == 0),
                   "chars_per_page": round(sum(ch) / len(ch)) if ch else None,
                   "zero_char_pages": sum(1 for x in ch if x == 0)}
            out["lanes"][lane] = row
            measured = len(lk) + len(ch)
            all_zero = measured > 0 and all(x == 0 for x in lk) and all(x == 0 for x in ch)
            if d["pages"] >= self.min_pages_per_lane and all_zero:
                zero.append(lane)
        out["zero_lanes"] = zero
        return out

    def check(self, when: str) -> dict:
        rep = self.report(when)
        self.reports.append(rep)
        if self.printer:
            self.printer("YIELD " + json.dumps(rep, default=str))
        if rep["zero_lanes"]:
            raise ReaderRefused(
                f"REFUSED_ZERO_YIELD_LANE: {rep['zero_lanes']} returned 0 links and 0 "
                f"characters on every page they loaded ({when}); a lane that yields "
                f"nothing is a broken reader, not a quiet night (2026-09-28: 51 of 51).")
        return rep


# ─────────────── LANE O: social pages, READ-ONLY, source_kind = social ────────
#
# Murat, 2026-09-28: "reddit x and other socials are logged in too". A social
# read is: navigate to a ticker's SEARCH or community URL (never type into a
# search box), scroll, read the visible text, store it with url, time and host.
# No claim extraction here. Rows carry `source_kind = "social"`: downstream, a
# social row may never originate an alert and never an order.

#: 2026-09-28 (the pool): the X url no longer carries `src=typed_query` -- the
#: page is NAVIGATED to, nothing was typed, and nothing here claims otherwise.
#: Reddit searches the investing subreddits together (restrict_sr), newest first.
REDDIT_SUBS = ("stocks", "investing", "wallstreetbets", "StockMarket", "options",
               "SecurityAnalysis", "ValueInvesting")
SOCIAL_URLS: dict[str, str] = {
    "x.com": "https://x.com/search?q=%24{ticker}&f=live",
    "reddit.com": ("https://www.reddit.com/r/" + "+".join(REDDIT_SUBS)
                   + "/search/?q={ticker}&restrict_sr=1&sort=new"),
    "stocktwits.com": "https://stocktwits.com/symbol/{ticker}",
}


def social_url(host: str, ticker: str) -> str:
    t = re.sub(r"[^A-Za-z0-9.\-]", "", ticker or "").upper()
    if not t:
        raise ReaderRefused(f"REFUSED_SOCIAL_TICKER: {ticker!r}")
    tpl = SOCIAL_URLS.get(host)
    if tpl is None:
        raise ReaderRefused(f"REFUSED_SOCIAL_HOST: {host!r} is not one of {sorted(SOCIAL_URLS)}")
    return tpl.format(ticker=t)


def social_root() -> Path:
    # from config, exactly as `corpus_root()`: a root rebuilt from `__file__`
    # lands inside the image on deploy and moves in the frozen desktop build
    return Path(_config.OPTIMUS_LEDGER_DIR) / "news_corpus" / "social"


def store_social(row: dict, *, root: Path | None = None) -> Path:
    """Append one social page to `news_corpus/social/<host>/<YYYY-MM-DD>.jsonl`
    (locked append). The row MUST carry `source_kind = "social"`."""
    if row.get("source_kind") != "social":
        raise ReaderRefused("REFUSED_SOCIAL_KIND: a social row must carry source_kind='social'")
    # 2026-09-28 (the pool puts the social hosts in the rotation): a social row
    # can never be marked as an alert's origin or an order's -- refused at the
    # one place every social row is written
    if row.get("alert_origin") or row.get("order_origin") or row.get("is_alert_origin"):
        raise ReaderRefused("REFUSED_SOCIAL_ALERT_ORIGIN: a social row may not be an alert's "
                            "or an order's origin")
    row = dict(row, never=sorted(set(row.get("never") or []) | {"alert_origin", "order"}))
    base = (root or social_root()) / str(row.get("host") or "unknown")
    day = str(row.get("read_utc") or datetime.now(timezone.utc).isoformat())[:10]
    path = base / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    DG.locked_append_line(path, json.dumps(row, ensure_ascii=False, default=str))
    return path


def read_social_page(reader: "Reader", url: str, *, ticker: str | None = None,
                     store: bool = True, root: Path | None = None) -> dict:
    """Load a social SEARCH / community URL in the reader's tab, scroll, read the
    visible text, store it tagged `source_kind = "social"`. No click, no typing:
    the client refuses both on a social host anyway."""
    if not is_social(url):
        raise ReaderRefused(f"REFUSED_SOCIAL_HOST: {url!r} is not on {social_hosts()}")
    t0 = time.time()
    reader.navigate(url)
    steps = reader.scroll_through()
    got = reader.driver.read_text(reader.tab, profile_name=reader.profile)
    if got.get("error") or not (got.get("text") or "").strip():
        raise ReaderRefused(f"REFUSED_EMPTY_READ: {url!r}: "
                            f"{(got.get('error') or 'no text returned')[:200]}")
    final = got.get("url") or url
    if not host_ok(final) or not is_social(final):
        raise ReaderRefused(f"REFUSED_LEFT_HOSTS: read landed on {final!r}")
    text = str(got.get("text") or "")
    row = {"source_kind": "social", "host": host_of(final), "url": final,
           "requested_url": url, "ticker": (ticker or "").upper() or None,
           "title": got.get("title"), "text": text, "chars": len(text),
           "read_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "scroll_steps": steps, "read_s": round(time.time() - t0, 2),
           "tab": reader.tab, "profile": reader.profile,
           "never": ["alert_origin", "order"]}
    if store:
        row["stored"] = str(store_social(row, root=root))
    reader.reads += 1
    reader.scrolled_reads += bool(steps)
    reader.blank()
    return row


# ───────────── the reader pool (2026-09-28 21:45 HKT): shared helpers ─────────
#
# Murat: "can openclaw read more, can it launch another chrome tabs to read too
# ... it needs to read wsj, barron, marketwatch per stock and the news from that
# too, it should navigate them, not just the stocks, and also the media too."
# `scripts/reader_pool.py` drives several tabs at once; these are the pure pieces
# it shares with the rest of the reader.

#: Social page classes. Anything but OK / BLANK stops that host for a cooling
#: period (`config.READER_HOST_COOL_S`); nothing is done to get around it.
SOCIAL_CLASSES = ("OK", "BLANK", "LOGIN_WALL", "INTERSTITIAL", "RATE_LIMITED", "CHALLENGE",
                  "REDIRECTED_OFF_HOST")
_SOCIAL_LOGIN_PATH = re.compile(r"/(i/flow/login|login|account/login|signin|sign-in)\b", re.I)
_SOCIAL_LOGIN_TEXT = re.compile(
    r"(sign in to x|log in to x|don.t miss what.s happening|log in to reddit|"
    r"continue with google|create your account|sign up for stocktwits|log in to stocktwits|"
    r"you must be logged in)", re.I)
_SOCIAL_RATE = re.compile(r"(rate limit|too many requests|you are over the daily limit|"
                          r"whoa there,? pardner|try again later|slow down)", re.I)
_SOCIAL_INTERSTITIAL = re.compile(r"(something went wrong\.? try reloading|"
                                  r"you.ve been blocked by network security|"
                                  r"this content is not available|age-restricted|"
                                  r"are you over 18)", re.I)
#: a logged-in results page is long; a wall is short
SOCIAL_WALL_MAX_CHARS = 1500


def classify_social(*, url: str, final_url: str | None, title: str | None,
                    text: str) -> str:
    """PURE. One of SOCIAL_CLASSES for a social page that was loaded and read.
    Order: off-host > blank > challenge > rate limit > login wall (a login
    URL, or login text on a SHORT page) > interstitial > OK."""
    fu = final_url or url or ""
    if fu and not fu.startswith("about:") and not (host_ok(fu) and is_social(fu)):
        return "REDIRECTED_OFF_HOST"
    body = (text or "").strip()
    if fu.startswith("about:") or len(body) < PAGE_MIN_CHARS:
        return "BLANK"
    head = f"{title or ''}\n{body[:1500]}"
    short = len(body) < SOCIAL_WALL_MAX_CHARS
    if _CHALLENGE.search(head) and len(body) < 4000:
        return "CHALLENGE"
    if _SOCIAL_RATE.search(head) and short:
        return "RATE_LIMITED"
    if _SOCIAL_LOGIN_PATH.search(urlsplit(fu).path or "") or (_SOCIAL_LOGIN_TEXT.search(head)
                                                              and short):
        return "LOGIN_WALL"
    if _SOCIAL_INTERSTITIAL.search(head) and short:
        return "INTERSTITIAL"
    return "OK"


#: Words that are tickers AND ordinary capitalised words; never counted as a
#: named ticker on their own.
TICKER_STOPWORDS = frozenset({"A", "I", "AI", "IT", "ON", "ALL", "ARE", "BE", "CAN", "FOR",
                              "GO", "HAS", "NOW", "ONE", "OR", "SO", "TV", "US", "USA", "CEO",
                              "CFO", "EPS", "GDP", "IPO", "ETF", "SEC", "FED", "NEW", "BIG",
                              "OUT", "AN", "AT", "BY", "DO", "HE", "IN", "IS", "OF", "TO",
                              "UP", "WE", "AM", "PM", "EV", "UK", "EU"})


def names_tickers(text: str, universe: set[str] | frozenset[str]) -> list[str]:
    """PURE. Universe tickers the text NAMES the way these sites print a
    ticker: `(NVDA)`, `(NASDAQ: NVDA)`, `ticker: NVDA`, `$NVDA`, or a quote chip
    `NVDA +1.2%` / `NVDA -0.4%`. A bare capitalised word is not a ticker."""
    if not text or not universe:
        return []
    found: list[str] = []
    pats = (r"\((?:[A-Za-z]+:\s*)?([A-Z]{1,5}(?:\.[A-Z])?)\)",
            r"ticker:\s*([A-Z]{1,5}(?:\.[A-Z])?)\b",
            r"\$([A-Z]{1,5}(?:\.[A-Z])?)\b",
            r"\b([A-Z]{1,5}(?:\.[A-Z])?)\s+[-+]?\d{1,3}(?:\.\d+)?%")
    for p in pats:
        for m in re.finditer(p, text):
            t = m.group(1).upper()
            if t in universe and t not in TICKER_STOPWORDS and t not in found:
                found.append(t)
    return found


def select_front_links(snapshot_text: str, link_pattern: str, *, now: datetime,
                       max_age_days: int = 3, limit: int = 12) -> dict:
    """Article links a SECTION FRONT shows, most prominent first (page order)
    and newest first where the page prints a date: the same chooser as a
    company page (`select_search_links`: host, pattern, no account/money text,
    no sponsored unit), each link carrying `position` (its rank among the
    page's matching links, 1 = first) for the `reached_by` record. Dated links
    older than `max_age_days` are skipped; undated ones keep page order."""
    sel = select_search_links(snapshot_text, link_pattern, now=now, max_age_days=max_age_days,
                              limit=10 ** 6)
    rows = [dict(lk, position=i + 1) for i, lk in enumerate(sel["links"])]

    def age(lk: dict) -> float:
        pv = lk.get("published_visible")
        if not pv:
            return float("inf")
        try:
            return (now - datetime.fromisoformat(pv)).total_seconds()
        except ValueError:
            return float("inf")
    # prominence first: a link in the first few positions keeps its place; below
    # them, dated links newest first, then undated ones in page order
    head = rows[:3]
    rest = sorted(rows[3:], key=lambda lk: (age(lk), lk["position"]))
    sel["links"] = (head + rest)[:limit]
    return sel


def free_memory_gb() -> float | None:
    """Free physical memory in GB (Windows `GlobalMemoryStatusEx`; elsewhere
    /proc/meminfo), None when it cannot be read. Never raises."""
    try:
        import ctypes
        import sys as _sys
        if _sys.platform == "win32":
            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = _MS()
            ms.dwLength = ctypes.sizeof(_MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):  # type: ignore[attr-defined]
                return round(ms.ullAvailPhys / 1e9, 2)
            return None
        for ln in Path("/proc/meminfo").read_text().splitlines():
            if ln.startswith("MemAvailable:"):
                return round(int(ln.split()[1]) * 1024 / 1e9, 2)
    except Exception:  # noqa: BLE001 -- unknown, never fatal
        return None
    return None
