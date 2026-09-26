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
  ALARM when the CV of gaps < 0.15).

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

LICENCE = "Dow Jones subscriber, personal research; not republished"

#: Hard stop regardless of the allowlist -- the tabs open beside the reader.
NEVER_HOSTS: tuple[str, ...] = ("mail.google.com", "app.alpaca.markets", "alpaca.markets",
                                "railway.com", "railway.app", "web.whatsapp.com")
#: Roles that are never clicked. A reader clicks LINKS.
DENY_ROLES: frozenset[str] = frozenset({"button", "textbox", "combobox", "checkbox",
                                        "radio", "searchbox", "form", "menuitem",
                                        "switch", "slider", "spinbutton", "option"})
#: Link text that reads like an account, money or messaging action.
DENY_LINK_TEXT = re.compile(
    r"sign\s*(out|in|up)|log\s*(out|in)|subscribe|subscription|buy\s+now|checkout|"
    r"register|my\s+account|account|settings|newsletter|gift|manage|customer\s+center|"
    r"cancel|upgrade|offer|trial|share|email|print|comment|podcast|video", re.I)

_SNAP_NODE = re.compile(r'^\s*-\s+(\w+)\s+"((?:[^"\\]|\\.)*)"(?:.*?\[ref=([^\]]+)\])?')
_SNAP_LINK = re.compile(r"^\s*\d+\.\s+(.*?)\s+->\s+(\S+)\s*$")


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def hosts() -> tuple[str, ...]:
    return tuple(_cfg("OPENCLAW_USER_TAB_HOSTS", ("wsj.com", "barrons.com", "marketwatch.com")))


def host_ok(url: str) -> bool:
    try:
        h = (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return False
    if not h or any(h == n or h.endswith("." + n) for n in NEVER_HOSTS):
        return False
    return any(h == d or h.endswith("." + d) for d in hosts())


#: Characters cmd.exe acts on. `openclaw_client._run` calls the `openclaw`
#: .cmd shim with `shell=True` on Windows, so an UNQUOTED `&` in an argument
#: ends the command: on 2026-09-26 both Big Money poll reads failed with
#: "'mod' is not recognized as an internal or external command" because the
#: snapshot's URLs carried `?refsec=big-money-poll&mod=...`. The root fix
#: (quote or avoid the shell in `_run`) is owed in openclaw_client.
_SHELL_META = re.compile(r"[&|^<>%\"]")


def shell_safe_url(url: str) -> str:
    """The same page without its tracking query when the query carries a
    cmd.exe metacharacter: `scheme://host/path`. Dow Jones article paths are
    complete on their own (`?mod=`, `&refsec=` are referral tags). A URL with
    no such character is returned unchanged."""
    if not url or not _SHELL_META.search(url):
        return url
    sp = urlsplit(url)
    bare = f"{sp.scheme}://{sp.netloc}{sp.path}"
    if _SHELL_META.search(bare):
        raise ReaderRefused(f"REFUSED_SHELL_UNSAFE_URL: {url!r} has a cmd metacharacter in "
                            f"its PATH; not passed to the shell")
    return bare


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


def ensure_attached(profile: str = "user", *, oc: Any = None, log: list | None = None,
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
    """`{nodes: [{role, name, ref}], links: [{text, url}]}` from `snapshot
    --format ai --urls` output (tree lines, then a `Links:` appendix)."""
    nodes, links, in_links = [], [], False
    for line in (text or "").splitlines():
        if line.strip() == "Links:":
            in_links = True
            continue
        if in_links:
            m = _SNAP_LINK.match(line)
            if m:
                links.append({"text": m.group(1).strip(), "url": m.group(2).strip()})
            continue
        m = _SNAP_NODE.match(line)
        if m:
            nodes.append({"role": m.group(1).lower(),
                          "name": m.group(2).replace('\\"', '"').strip(),
                          "ref": (m.group(3) or "").strip() or None})
    return {"nodes": nodes, "links": links}


def select_links(snapshot_text: str, link_pattern: str, *, text_pattern: str | None = None,
                 limit: int | None = None) -> list[dict]:
    """Links the page SHOWS that match `link_pattern` (on the URL) and, if
    given, `text_pattern` (on the link text). `[{text, url, ref}]`, deduped by
    URL, in page order. A decoy (wrong host, account/money text, a button, a
    URL that does not match) is never returned."""
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
        if DENY_LINK_TEXT.search(t) or (txt_re and not txt_re.search(t)):
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
                and not DENY_LINK_TEXT.search(n["name"])
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
    waits: list[float] = field(default_factory=list)
    targets: list[float] = field(default_factory=list)
    _rng: Any = field(default=None, repr=False)

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

    def acquire(self, what: str = "page", host: str = "") -> float:
        """Sleep until the next load is allowed, record it, return seconds waited.
        Raises `ReaderRefused` when the hourly, daily or per-host daily cap is spent."""
        now = self.now_fn()
        rows = [r for r in self._rows() if now - r[0] < timedelta(days=1)]
        if len(rows) >= self.max_per_day:
            raise ReaderRefused(f"REFUSED_THROTTLE_DAY: {len(rows)} page loads in 24 h "
                                f">= {self.max_per_day}")
        if host and sum(1 for r in rows if r[1] == host) >= self.max_per_day_per_host:
            raise ReaderRefused(f"REFUSED_THROTTLE_HOST_DAY: >= {self.max_per_day_per_host} "
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
        if wait > 0:
            self.sleep_fn(wait)
        self.waits.append(round(wait, 2))
        self.targets.append(target)
        stamp = self.now_fn() if wait > 0 else now
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp.isoformat()} {host or '-'} {target}\n")
        return wait


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


def acquire_reader_lock(path: Path | None = None, *, pid: int | None = None) -> Path:
    """ONE reading session at a time, across processes. A lock whose PID is
    dead is stale and is taken over (and said so in the lock itself)."""
    import os
    p = Path(path) if path else lock_path()
    me = int(pid if pid is not None else os.getpid())
    if p.exists():
        try:
            other = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            other = {}
        opid = int(other.get("pid") or 0)
        if opid and opid != me and _pid_alive(opid):
            raise ReaderRefused(f"REFUSED_READER_BUSY: another reading session (pid {opid}, "
                                f"since {other.get('since')}) holds {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": me, "since": datetime.now(timezone.utc).isoformat(
        timespec="seconds")}), encoding="utf-8")
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


def footprint_receipt(log: list[dict], *, scrolled: int = 0, reads: int = 0,
                      out_dir: Path | None = None, write: bool = True) -> dict:
    """What this session looked like from the site's side: the gaps between
    page loads, pages/hour, the coefficient of variation of the gaps, and the
    share of reads that scrolled. `verdict` is `HUMAN_PACE_OK`, `ALARM: ...`
    (CV < 0.15 -- pacing collapsed to a constant) or `CANNOT DETERMINE` (< 3
    gaps), never a bare boolean."""
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
    if write:
        d = Path(out_dir) if out_dir else Path(_config.OPTIMUS_LEDGER_DIR) / "web_reader"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"footprint_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        p.write_text(json.dumps(rc, indent=1), encoding="utf-8")
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
    from backend.services import dowjones_claims as DC
    from backend.services import news_registry as NR
    root = Path(root) if root else corpus_root()
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
           "column": art.get("column"), "origin": origin, "licence": LICENCE,
           "text": art.get("text") or ""}
    rec["pit_grade"] = NR.effective_pit_grade(
        {"published_utc": rec["published_utc"], "first_seen_utc": seen,
         "pit_grade": "first_seen_only"})
    for k in ("tab", "profile", "attached_to", "read_s"):
        if k in art:
            rec[k] = art[k]
    p = root / pub / day / f"{sha}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

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


# ─────────────────────────────── the reader ─────────────────────────────────

@dataclass
class Reader:
    """One reading session in one tab this process opened.

    `driver` is `openclaw_client` (or a stub in tests). Every page load goes
    through `throttle.acquire`. `max_pages` is the session cap.
    """

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
    _lock_path: Path | None = None

    def __post_init__(self) -> None:
        if self.driver is None:
            from backend.services import openclaw_client as OC
            self.driver = OC
        if self.lock:
            self._lock_path = acquire_reader_lock()

    def close(self, *, write_footprint: bool = True) -> dict | None:
        """Release the one-reader lock and write the session's footprint."""
        fp = None
        if write_footprint:
            fp = footprint_receipt(self.log, scrolled=self.scrolled_reads, reads=self.reads)
        if self._lock_path is not None:
            release_reader_lock(self._lock_path)
            self._lock_path = None
        return fp

    def scroll_through(self) -> int:
        """2-3 PageDown presses with jittered 1-3 s pauses -- a person reads
        down a page; an instant extraction with no scroll is the tell."""
        rng = self.throttle._rng
        n = int(rng.integers(self.scroll_steps[0], self.scroll_steps[1] + 1))
        done = 0
        for _ in range(n):
            self.driver.browser("wait", "--time", str(int(rng.uniform(1000, 3000))),
                                profile_name=self.profile, target_id=self.tab)
            r = self.driver.browser("press", "PageDown", profile_name=self.profile,
                                    target_id=self.tab)
            self._check_still_on_host(r)
            done += 1
        return done

    def _page(self, what: str, url: str | None) -> float:
        if self.pages >= self.max_pages:
            raise ReaderRefused(f"REFUSED_SESSION_CAP: {self.pages} pages >= {self.max_pages}")
        if url is not None and not host_ok(url):
            raise ReaderRefused(f"REFUSED_HOST: {url!r} is not on {hosts()}")
        host = (urlsplit(url or "").hostname or "").lower().removeprefix("www.") if url else ""
        waited = self.throttle.acquire(what, host=host)
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
        shown = url
        url = shell_safe_url(url)
        self._page("navigate", url)
        if url != shown:
            self.log[-1]["url_shown"] = shown
        r = self.driver.browser("navigate", url, profile_name=self.profile, target_id=self.tab)
        self._check_still_on_host(r)
        self.driver.browser("wait", "--time", str(self.wait_ms),
                            profile_name=self.profile, target_id=self.tab)

    def snapshot(self) -> str:
        r = self.driver.browser("snapshot", "--format", "ai", "--urls", "--limit", "900",
                                profile_name=self.profile, target_id=self.tab)
        self.last_snapshot = r.get("stdout") or ""
        return self.last_snapshot

    def read_listing(self, url: str, link_pattern: str, *, text_pattern: str | None = None,
                     limit: int | None = None) -> list[dict]:
        """navigate -> wait -> snapshot -> links chosen FROM the snapshot."""
        self.navigate(url)
        return select_links(self.snapshot(), link_pattern, text_pattern=text_pattern,
                            limit=limit)

    def read_article(self, link: dict | str, *, column: str | None = None,
                     origin: str = "web_reader", store: bool = True) -> dict:
        """click the link's ref (when the last snapshot shows it as a link) or
        navigate to its URL -> wait -> fixed innerText read -> clean -> store."""
        from backend.services import dowjones_claims as DC
        url = link if isinstance(link, str) else link.get("url")
        ref = None if isinstance(link, str) else link.get("ref")
        t0 = time.time()
        if ref and self.last_snapshot and ref_is_clickable(self.last_snapshot, ref):
            self._page("click", url)
            r = self.driver.browser("click", ref, profile_name=self.profile, target_id=self.tab)
            self._check_still_on_host(r)
            self.driver.browser("wait", "--time", str(self.wait_ms),
                                profile_name=self.profile, target_id=self.tab)
        else:
            self.navigate(url)
        steps = self.scroll_through()
        self.reads += 1
        self.scrolled_reads += bool(steps)
        got = self.driver.read_text(self.tab, profile_name=self.profile)
        if got.get("error") or not (got.get("text") or "").strip():
            # An empty read is a FAILURE with a name, never a page with no text.
            raise ReaderRefused(f"REFUSED_EMPTY_READ: {url!r}: "
                                f"{(got.get('error') or 'no text returned')[:200]}")
        final_url = got.get("url") or url
        if not host_ok(final_url):
            raise ReaderRefused(f"REFUSED_LEFT_HOSTS: read landed on {final_url!r}")
        raw = got.get("text") or ""
        title = got.get("title") or (None if isinstance(link, str) else link.get("text"))
        text = clean_text(raw, title)
        pub = DC.publisher_of(final_url, text)
        art = {"url": final_url, "title": title, "byline": parse_byline(text),
               "published_utc": parse_published(text), "text": text,
               "first_seen_utc": DC.now_iso(), "chars": len(text), "raw_chars": len(raw),
               "publisher": pub, "origin": origin, "tab": self.tab, "profile": self.profile,
               "attached_to": got.get("attached_to"),
               "paywall_suspected": bool(re.search(r"subscribe to continue|to keep reading|"
                                                   r"choose your .* subscription", raw, re.I)),
               "column": column or DC.column_of(final_url, title or "", text, pub)}
        art["sha"] = DC.text_sha(text)
        art["scroll_steps"] = steps
        art["read_s"] = round(time.time() - t0, 2)
        if store and text:
            art["stored"] = store_article(art)
        self.last_snapshot = ""
        return art
