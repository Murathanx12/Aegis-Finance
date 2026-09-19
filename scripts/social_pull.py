"""S0 — THE SOCIAL COLLECTOR. Reddit posts AND comments, YouTube search. Keys, no LLM.

    python -m scripts.social_pull --dry-run         # what it WOULD ask, no request
    python -m scripts.social_pull --source reddit
    python -m scripts.social_pull                   # both sources, one receipt

Chunk 20 T2, from `docs/research_notes/2026-09-19/spec_social_video_pipeline.md`
§1 (the source table), §3.1 (where each source lives) and §3.2 (the row shape).
`scripts/hiring_pull.py` is the SHAPE this copies: a collector outside
`news_pull.py` that keeps the same row contract, the same cursor/receipt
discipline and the same "refuse by name, never crash" rule, because its auth
does not fit `RunContext.http_get`'s bearer-token-or-none model.

WHY NOT IN `news_pull.py`
========================
Reddit is OAuth2 with a token refresh (PRAW owns that) and YouTube is a METERED
quota rather than a rate limit — 10,000 units a day, `search.list` costing
**100 of them**, resetting at midnight PACIFIC and not UTC. `news_pull`'s
`RunContext` has no place to carry either, and a receipt with no quota field is
how a 100-search daily allowance is spent by lunchtime with nobody able to see
it happen.

THE TWO KEYS, AND THE REFUSAL THAT IS THE LIVE PATH TODAY
=========================================================
Neither key exists in this environment on 2026-09-19. That is not a bug to work
around: **the refusal IS the tested path**, exactly as `alpaca_benzinga_news`'s
is in `news_pull`. Reddit refuses `REDDIT_KEYS_ABSENT` naming
`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`; YouTube
refuses `YOUTUBE_KEY_ABSENT` naming `YOUTUBE_API_KEY`. The run still writes a
receipt and still exits 0, because a source with no key is a fact about the
environment and not a failure of the pass.

**NAMES ONLY, EVER.** Nothing in this file puts a key VALUE in a log line, a
receipt, an exception message or a row.
`test_social_pull.py::test_no_key_value_can_reach_a_log_or_a_receipt` walks
this module's AST to keep that true, and a second test sets both keys to a
sentinel and greps the whole receipt and stdout for it.

WHAT IS NOT BUILT, AND WHY — read this before adding it
=======================================================
* **Transcripts.** `youtube-transcript-api` is grey (no ToS grant) and, per the
  spec's own source table, **cloud-provider IPs are actively blocked in 2026**;
  the working configuration is a rotating residential proxy at $20-50/mo. So
  the transcript step refuses by name, `TRANSCRIPT_SOURCE_NOT_LAWFUL_HERE`,
  with that reason on the receipt rather than being silently skipped.
* **X/Twitter.** Pay-per-read ($0.005/read, capped 2M/mo), no free self-serve
  tier after 2026. The spec puts it OFF the lab's automatic cadence entirely
  (§4.3), and an unattended loop against a metered API is the same failure
  class as the $448,555 unattended-fleet exposure already logged for
  2026-09-18. It is not in this file and must not be added to it without an
  operator-file gate.
* **Instagram.** No lawful path for this use case (spec §1: Graph API reads
  only accounts the app owns; Basic Display died 2024-12-04; scraping violates
  ToS and carries GDPR exposure on comment authors). Do not build a collector.
* **StockTwits.** UNVERIFIED terms — it needs a live probe before a parser.

WHAT THIS FILE DOES NOT DO
==========================
It computes no feature, types nothing, labels nothing. `pit_grade` is
`index_state` for every row here (a platform can edit or delete a comment after
posting and we cannot detect a backfill), so `label_source` is false and no
return may ever be labelled from these timestamps — invariant 20, the same rule
the three Reddit RSS rows already carry. `scripts/night_social_features.py`
reads what this writes.

LICENCE: PRODUCT_EXPERIMENT. No order path, no LLM, no claim.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402
from backend.services import news_entities as entities  # noqa: E402
from scripts.news_pull import call_with_timeout  # noqa: E402

JOB = "S0_social_pull"
LICENCE = "PRODUCT_EXPERIMENT"

#: The sources this file knows. An id not here is a refusal at parse, the same
#: contract `news_registry.UnknownSource` gives lane N.
SOURCES = ("reddit", "youtube")

#: ENV VARIABLE NAMES. Names are all this file ever handles.
REDDIT_KEY_NAMES = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
YOUTUBE_KEY_NAMES = ("YOUTUBE_API_KEY",)

#: Every refusal this collector can return, by name.
REFUSALS = (
    "REDDIT_KEYS_ABSENT",
    "YOUTUBE_KEY_ABSENT",
    "PRAW_NOT_INSTALLED",
    "YOUTUBE_QUOTA_SPENT",
    "TRANSCRIPT_SOURCE_NOT_LAWFUL_HERE",
    "UNKNOWN_SOURCE",
)

#: THE SUBREDDIT LIST, DECLARED HERE FIRST. The spec names Reddit and leaves
#: the list open; these are the subs the 2026-09-11 social survey actually
#: measured (`research_social.md` line 90: r/options 1.3-1.4M, r/ValueInvesting
#: 794K, r/SecurityAnalysis 180-213K "highest S/N", r/wallstreetbets largest and
#: lowest S/N, r/algotrading the systematic one), plus r/stocks and r/investing
#: which that line names beside them.
#:
#: `wallstreetbets` is in the list for a reason that is not enthusiasm: §2.3's
#: null IS the WSB peak-attention finding (positions opened at peak attention
#: realize -8.5% HPR), and a hype-lateness variable computed without the sub
#: that finding came from could not be compared with it.
#:
#: Frozen here so a pre-registration can CITE the list rather than re-derive a
#: second one that quietly differs — `hiring_pull.AI_TITLE_TERMS`' reason.
SUBREDDITS: tuple[str, ...] = (
    "wallstreetbets", "stocks", "investing", "options",
    "ValueInvesting", "SecurityAnalysis", "algotrading",
)

#: THE YOUTUBE QUERY LIST, DECLARED HERE FIRST. The spec names `search.list` and
#: leaves the queries open. At 100 units a search and a 10,000-unit day, the
#: whole allowance is 100 searches — so the list is short on purpose and is
#: about the EVENTS the pipeline's variables are keyed to, not about channels.
YOUTUBE_QUERIES: tuple[str, ...] = (
    "earnings call analysis",
    "stock earnings breakdown this week",
    "supply constraint chips shortage stock",
    "guidance cut stock reaction",
    "semiconductor capacity outlook",
)

#: Per-request wall bound, inside `call_with_timeout` (a daemon-thread box, so
#: a hung TLS handshake is abandoned and not waited on — 2026-09-13 paid two
#: hours for the version of this that trusted a library's own timeout).
REQUEST_TIMEOUT_S = 30.0

#: Seconds between calls to ONE provider. Single-threaded, so this IS the rate
#: limit. Reddit's documented ceiling is 100 queries/min per OAuth client; 1.0 s
#: is well inside it and PRAW paces itself on top.
PACE_S = 1.0

#: A response bigger than this is refused unparsed.
MAX_BYTES = 8 * 1024 * 1024

#: Body cap per row. Reddit self-posts run long; a comment rarely does.
MAX_TEXT = 8000

#: YouTube's quota day resets at MIDNIGHT PACIFIC, not UTC. Getting this wrong
#: does not fail — it silently spends tomorrow's allowance on today's evening.
YOUTUBE_QUOTA_TZ = ZoneInfo("America/Los_Angeles")

#: `$AAPL`. Validated against the issuer table before it counts, so `$YOLO` is
#: not a ticker. `news_entities.resolve` applies the same rule and also matches
#: company NAMES; this pattern exists so a receipt can count cashtags
#: separately from name matches.
CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,5})\b")

ROW_KEYS = (
    "source", "kind", "first_seen_utc", "id", "parent_id", "channel",
    "author_pseudonym", "title", "text", "url", "created_utc_provider",
    "ticker_mentions", "ticker_rules", "engagement", "pit_grade",
)


class SocialRefused(RuntimeError):
    """The collector cannot run as asked, and says which name. Never silent."""


# --------------------------------------------------------------------- paths

def social_dir() -> Path:
    """`<DATA_DIR>/optimus/social` — WRITTEN state, so it follows DATA_DIR."""
    return Path(_config.DATA_DIR) / "optimus" / "social"


def rows_path(source: str, month: str) -> Path:
    return social_dir() / f"{source}_{month}.jsonl"


def cursor_path(source: str) -> Path:
    return social_dir() / f"_cursor_{source}.json"


def receipt_path(stamp: str) -> Path:
    return social_dir() / f"_receipt_{stamp}.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


def _month(dt: datetime | None = None) -> str:
    return (dt or _now()).strftime("%Y-%m")


def quota_day(now: datetime | None = None) -> str:
    """Today, on YOUTUBE'S clock. See `YOUTUBE_QUOTA_TZ`."""
    return (now or _now()).astimezone(YOUTUBE_QUOTA_TZ).date().isoformat()


# --------------------------------------------------------------- credentials

def key_status() -> dict:
    """WHICH NAMES are set. Names and booleans only — never a value, never a
    length, never a prefix: a receipt that printed four characters of a secret
    would be a receipt that leaked a secret slowly."""
    return {
        "reddit": {name: bool(os.getenv(name)) for name in REDDIT_KEY_NAMES},
        "youtube": {name: bool(os.getenv(name)) for name in YOUTUBE_KEY_NAMES},
    }


def missing_keys(names: tuple[str, ...]) -> list[str]:
    return [n for n in names if not os.getenv(n)]


# ------------------------------------------------------------------ fetching

def _http_get(url: str) -> tuple[int, bytes]:
    """THE network door for the YouTube half. Every test replaces this name.

    A non-200 comes back as its status with an empty body rather than an
    exception: a 403 from YouTube is usually "quota exceeded", which is an
    ANSWER to the question this collector asks, not an error in asking it.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:  # noqa: S310
            return int(r.status), r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return int(exc.code), b""


def _user_agent() -> str:
    """A contactable UA. Reddit's app policy REQUIRES a descriptive one and
    429s without it; the value, when it exists, is a key NAME's content and is
    passed to the client rather than printed."""
    return ("aegis-finance-research/1.0 "
            "(+https://github.com/Murathanx12/Aegis-Finance)")


def reddit_client(*, praw_module=None):
    """A read-only PRAW client, or a named refusal. Never a key in a message.

    `check_for_updates=False` is not decoration: PRAW's default configuration
    pings PyPI on construction, and a collector that makes an unasked-for
    network call on every tick is a collector nobody can bound.
    """
    missing = missing_keys(REDDIT_KEY_NAMES)
    if missing:
        raise SocialRefused(
            f"REDDIT_KEYS_ABSENT: {', '.join(missing)} not set. Create a SCRIPT "
            f"app at www.reddit.com/prefs/apps and put the client id and secret "
            f"in .env under those NAMES; REDDIT_USER_AGENT must be a "
            f"descriptive string per Reddit's app policy or the API 429s.")
    if praw_module is None:
        try:
            import praw as praw_module  # noqa: PLC0415
        except Exception as exc:                                   # noqa: BLE001
            raise SocialRefused(
                f"PRAW_NOT_INSTALLED: {type(exc).__name__}. `pip install praw` "
                f"— it is in backend/requirements.txt; this environment has "
                f"not installed it.") from exc
    return praw_module.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT") or _user_agent(),
        check_for_updates=False,
        check_for_async=False,
    )


def youtube_search_url(query: str, *, published_after: str = "",
                       max_results: int = 25) -> str:
    """The `search.list` URL. The KEY IS NOT IN IT.

    The api key is appended by `_youtube_call`, which is also the only place it
    is read — so no URL that reaches a log, a receipt or an exception message
    has ever carried one.
    """
    params = {
        "part": "snippet", "type": "video", "order": "date",
        "maxResults": int(max_results), "q": query,
    }
    if published_after:
        params["publishedAfter"] = published_after
    return "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params)


def _youtube_call(url: str, *, fetch: Callable[[str], tuple[int, bytes]] | None = None
                  ) -> tuple[int, Any]:
    fetch = fetch or _http_get
    key = os.getenv("YOUTUBE_API_KEY") or ""
    full = url + ("&" if "?" in url else "?") + "key=" + urllib.parse.quote(key)
    status, body = call_with_timeout(lambda: fetch(full), REQUEST_TIMEOUT_S,
                                     "youtube search.list")
    if status != 200 or not body:
        return status, None
    try:
        return status, json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return status, None


# ---------------------------------------------------------------- the tickers

def ticker_mentions(text: str, *, tbl=None) -> tuple[list[str], dict]:
    """`(symbols, {symbol: rule})` — cashtags AND the shipped name table.

    One resolver, not two: `news_entities.resolve` already validates a cashtag
    against `issuers.csv` (so `$YOLO` is not a ticker) and also matches company
    names with an ambiguity guard. Writing a second matcher here would be a
    second definition of "this row is about NVDA" that could disagree with lane
    N's on the same sentence.
    """
    res = entities.resolve(text or "", tbl=tbl)
    return list(res.tickers), dict(res.how)


def cashtag_count(text: str, *, tbl=None) -> int:
    """How many cashtags in the text name a KNOWN symbol. For the receipt only."""
    t = tbl or entities.tables()
    return sum(1 for m in CASHTAG_RE.finditer(text or "")
               if m.group(1).upper() in t.symbols)


# ------------------------------------------------------------------ the rows

def _row(*, source: str, kind: str, rid: str, parent_id: str, channel: str,
         author: str, title: str, text: str, url: str, created: Any,
         engagement: dict, tbl=None, first_seen: datetime | None = None) -> dict:
    """One social row. `first_seen_utc` is OURS, written at write time.

    ENGAGEMENT IS AS-OF FIRST SEEN AND IS NEVER RE-FETCHED (spec §3.2). A
    later-fetched upvote count is itself a look-ahead: a WSB post's visible
    score TODAY is not what it was when the post was made, and a backtest that
    reads today's number has read the future.
    """
    body = (text or "")[:MAX_TEXT]
    syms, rules = ticker_mentions(f"{title or ''}\n{body}", tbl=tbl)
    return {
        "source": source,
        "kind": kind,
        "first_seen_utc": _iso(first_seen),
        "id": str(rid or ""),
        "parent_id": str(parent_id or ""),
        "channel": channel or "",
        "author_pseudonym": str(author or ""),
        "title": (title or "")[:500],
        "text": body,
        "url": url or "",
        "created_utc_provider": str(created or ""),
        "ticker_mentions": syms,
        "ticker_rules": rules,
        "engagement": dict(engagement or {}),
        # index_state, for every row here: a platform can edit or delete a
        # comment after posting and we have no way to detect the backfill.
        "pit_grade": "index_state",
    }


def _read_cursor(source: str) -> dict:
    p = cursor_path(source)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def _append(source: str, rows: list[dict]) -> dict:
    """Append rows to their MONTH file. Append-only; nothing here rewrites."""
    by_month: dict[str, list[dict]] = {}
    for r in rows:
        dt = datetime.fromisoformat(r["first_seen_utc"])
        by_month.setdefault(_month(dt), []).append(r)
    written: dict[str, int] = {}
    for month, chunk in sorted(by_month.items()):
        p = rows_path(source, month)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for r in chunk:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        written[str(p)] = len(chunk)
    return written


def seen_ids(source: str, months: int = 2) -> set[str]:
    """Ids already on disk for this source, from the last `months` files.

    Bounded for `news_pull.DEDUPE_LOOKBACK_DAYS`' reason: an unbounded seen-set
    in a cursor grows without limit, and a comment that reappears two months
    later is a new row by any useful definition.
    """
    out: set[str] = set()
    d = social_dir()
    if not d.is_dir():
        return out
    files = sorted(d.glob(f"{source}_*.jsonl"))[-max(1, months):]
    for p in files:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                out.add(str(json.loads(line).get("id") or ""))
            except json.JSONDecodeError:
                continue
    out.discard("")
    return out


# ----------------------------------------------------------------- the pulls

def pull_reddit(*, client=None, subreddits: tuple[str, ...] = SUBREDDITS,
                posts_per_sub: int | None = None,
                comments_per_post: int | None = None,
                pace_s: float = PACE_S, dry_run: bool = False,
                budget_s: float = 0.0) -> dict:
    """Posts AND comments, per subreddit. The comments are the new half.

    The three registry rows that exist today (`reddit_algotrading_rss` and
    friends) are POST RSS only — `news_sources.yaml` says so in as many words.
    Comment TREES are what §2.2's dispersion variable is computed over and no
    source in this repo has ever pulled one.

    `client` is injectable so every test drives this without PRAW, a key or a
    socket.
    """
    t0 = time.time()
    posts_per_sub = int(_config.SOCIAL_REDDIT_POSTS_PER_SUB
                        if posts_per_sub is None else posts_per_sub)
    comments_per_post = int(_config.SOCIAL_REDDIT_COMMENTS_PER_POST
                            if comments_per_post is None else comments_per_post)
    out: dict[str, Any] = {
        "source": "reddit", "status": "OK", "refused": "", "rows": 0,
        "posts": 0, "comments": 0, "dupes": 0, "calls": 0, "failures": [],
        "subreddits": list(subreddits),
        "posts_per_sub": posts_per_sub, "comments_per_post": comments_per_post,
        "key_names": list(REDDIT_KEY_NAMES),
    }
    if dry_run:
        out["status"] = "DRY_RUN"
        out["planned_calls"] = len(subreddits) * (1 + posts_per_sub)
        out["headline"] = (f"DRY RUN: would read {len(subreddits)} subreddit(s), "
                           f"<= {posts_per_sub} post(s) each and their comment trees")
        return out

    if client is None:
        try:
            client = reddit_client()
        except SocialRefused as exc:
            out["status"] = "REFUSED"
            out["refused"] = str(exc).split(":", 1)[0]
            out["failures"].append(str(exc))
            out["headline"] = str(exc)[:200]
            return out

    tbl = entities.tables()
    known = seen_ids("reddit")
    rows: list[dict] = []
    for i, sub in enumerate(subreddits):
        if budget_s and (time.time() - t0) > budget_s:
            out["failures"].append(
                f"wall-clock budget of {budget_s:.0f}s spent after {i} subreddit(s); "
                f"this is a BUDGET, not a failure — the next run continues.")
            break
        if i and pace_s:
            time.sleep(pace_s)
        try:
            out["calls"] += 1
            submissions = call_with_timeout(
                lambda: list(client.subreddit(sub).new(limit=posts_per_sub)),  # noqa: B023
                REQUEST_TIMEOUT_S, f"reddit r/{sub}")
        except Exception as exc:                                   # noqa: BLE001
            out["failures"].append(f"r/{sub}: {type(exc).__name__}: {exc}")
            continue
        for sub_post in submissions or []:
            pid = str(getattr(sub_post, "id", "") or "")
            if not pid:
                out["dupes"] += 1
                continue
            if f"t3_{pid}" in known:
                # A POST WE ALREADY HAVE STILL GETS ITS TREE READ, and the
                # first version of this loop `continue`d here. That bug was
                # found by the test that asserts a second pass sees three
                # dupes: a post is written once and then ACCUMULATES comments
                # for days, so skipping the tree of every known post would have
                # collected only the comments that existed in the first minutes
                # of a post's life — and §2.2's dispersion variable is computed
                # over exactly the comments that arrive afterwards.
                out["dupes"] += 1
            else:
                rows.append(_row(
                    source="reddit", kind="post", rid=f"t3_{pid}", parent_id="",
                    channel=f"r/{sub}",
                    author=_pseudonym(getattr(sub_post, "author", None)),
                    title=str(getattr(sub_post, "title", "") or ""),
                    text=str(getattr(sub_post, "selftext", "") or ""),
                    url=_permalink(sub_post),
                    created=getattr(sub_post, "created_utc", ""),
                    engagement={"score": _int(getattr(sub_post, "score", None)),
                                "num_comments": _int(getattr(sub_post, "num_comments", None)),
                                "upvote_ratio": _float(getattr(sub_post, "upvote_ratio", None))},
                    tbl=tbl))
                out["posts"] += 1
            try:
                out["calls"] += 1
                comments = call_with_timeout(
                    lambda: _comment_list(sub_post, comments_per_post),  # noqa: B023
                    REQUEST_TIMEOUT_S, f"reddit comments {pid}")
            except Exception as exc:                               # noqa: BLE001
                out["failures"].append(f"{pid} comments: {type(exc).__name__}: {exc}")
                continue
            for c in comments or []:
                cid = str(getattr(c, "id", "") or "")
                if not cid or f"t1_{cid}" in known:
                    out["dupes"] += 1
                    continue
                rows.append(_row(
                    source="reddit", kind="comment", rid=f"t1_{cid}",
                    parent_id=str(getattr(c, "parent_id", "") or f"t3_{pid}"),
                    channel=f"r/{sub}",
                    author=_pseudonym(getattr(c, "author", None)),
                    title="", text=str(getattr(c, "body", "") or ""),
                    url=_permalink(c),
                    created=getattr(c, "created_utc", ""),
                    engagement={"score": _int(getattr(c, "score", None))},
                    tbl=tbl))
                out["comments"] += 1

    out["rows"] = len(rows)
    out["written"] = _append("reddit", rows) if rows else {}
    out["cashtag_rows"] = sum(1 for r in rows if "cashtag" in set(r["ticker_rules"].values()))
    out["rows_with_a_ticker"] = sum(1 for r in rows if r["ticker_mentions"])
    _write_json(cursor_path("reddit"), {
        "source": "reddit", "last_run_utc": _iso(),
        "runs": int(_read_cursor("reddit").get("runs", 0)) + 1,
        "rows_written_total": int(_read_cursor("reddit").get("rows_written_total", 0)) + len(rows),
        "note": ("dedupe reads the MONTH FILES, not this cursor: a set read "
                 "from the rows on disk cannot disagree with the rows on disk"),
    })
    out["wall_s"] = round(time.time() - t0, 1)
    out["headline"] = (f"{out['posts']} post(s) and {out['comments']} comment(s) "
                       f"over {len(subreddits)} subreddit(s); "
                       f"{out['rows_with_a_ticker']} row(s) name a symbol")
    return out


def _comment_list(submission, limit: int) -> list:
    """`replace_more(limit=0)` then a flat list, capped.

    `replace_more(limit=0)` DROPS the "load more comments" stubs instead of
    expanding them — each expansion is another API call, and an uncapped
    expansion on a 4,000-comment WSB thread is a minute of somebody else's rate
    limit for the tail of a distribution. The cap is declared and printed, so
    the dispersion variable's denominator is known rather than assumed.
    """
    forest = getattr(submission, "comments", None)
    if forest is None:
        return []
    replace = getattr(forest, "replace_more", None)
    if callable(replace):
        replace(limit=0)
    lister = getattr(forest, "list", None)
    items = list(lister()) if callable(lister) else list(forest)
    return items[: int(limit)]


def _pseudonym(author) -> str:
    """Reddit authors are pseudonymous and stay that way. A deleted author is
    `[deleted]`, which is a fact and not an empty string."""
    if author is None:
        return "[deleted]"
    return str(getattr(author, "name", author) or "[deleted]")


def _permalink(obj) -> str:
    p = getattr(obj, "permalink", "") or ""
    p = str(p)
    return f"https://www.reddit.com{p}" if p.startswith("/") else p


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pull_youtube(*, queries: tuple[str, ...] = YOUTUBE_QUERIES,
                 fetch: Callable[[str], tuple[int, bytes]] | None = None,
                 pace_s: float = PACE_S, dry_run: bool = False,
                 now: datetime | None = None) -> dict:
    """`search.list` per declared query, with the quota counted BEFORE the call.

    100 units a search against a 10,000-unit day is **100 searches, total** —
    the tightest budget in this pipeline and the one a loop can exhaust before
    anybody looks. So the spend is written to the cursor BEFORE each call
    (`night_factory`'s "record the dispatch before the call" lesson: a record
    written after a return that never came was never written), and the day is
    computed on YouTube's PACIFIC clock, not UTC.
    """
    t0 = time.time()
    unit_cost = int(_config.SOCIAL_YOUTUBE_SEARCH_UNITS)
    cap = int(_config.SOCIAL_YOUTUBE_DAILY_UNITS)
    day = quota_day(now)
    cursor = _read_cursor("youtube")
    spent = int(cursor.get("units_spent", 0)) if cursor.get("quota_day") == day else 0
    out: dict[str, Any] = {
        "source": "youtube", "status": "OK", "refused": "", "rows": 0,
        "searches": 0, "dupes": 0, "calls": 0, "failures": [],
        "queries": list(queries), "key_names": list(YOUTUBE_KEY_NAMES),
        "quota": {"day_pacific": day, "unit_cost_per_search": unit_cost,
                  "daily_cap_units": cap, "units_spent_before": spent,
                  "searches_left_before": max(0, (cap - spent) // unit_cost),
                  "reset": "midnight America/Los_Angeles, NOT UTC"},
        "transcripts": transcript_refusal(),
    }
    if dry_run:
        out["status"] = "DRY_RUN"
        out["planned_calls"] = len(queries)
        out["planned_units"] = len(queries) * unit_cost
        out["headline"] = (f"DRY RUN: would spend {len(queries) * unit_cost} of "
                           f"{cap - spent} units left today ({len(queries)} search(es))")
        return out

    missing = missing_keys(YOUTUBE_KEY_NAMES)
    if missing:
        out["status"] = "REFUSED"
        out["refused"] = "YOUTUBE_KEY_ABSENT"
        out["failures"].append(
            f"YOUTUBE_KEY_ABSENT: {', '.join(missing)} not set. Enable the API at "
            f"console.cloud.google.com/apis/library/youtube.googleapis.com and "
            f"create a key at console.cloud.google.com/apis/credentials; the free "
            f"10,000-unit day needs no card.")
        out["headline"] = out["failures"][0][:200]
        return out

    tbl = entities.tables()
    known = seen_ids("youtube")
    rows: list[dict] = []
    for i, q in enumerate(queries):
        if spent + unit_cost > cap:
            out["refused"] = "YOUTUBE_QUOTA_SPENT"
            out["failures"].append(
                f"YOUTUBE_QUOTA_SPENT: {spent} of {cap} units used on {day} "
                f"(Pacific); the next search costs {unit_cost} and would exceed "
                f"it. {len(queries) - i} query/queries not asked.")
            break
        if i and pace_s:
            time.sleep(pace_s)
        # Charged BEFORE the call, and persisted before the call returns: a
        # request that times out still spent the units at Google's end.
        spent += unit_cost
        _write_json(cursor_path("youtube"), {
            "source": "youtube", "quota_day": day, "units_spent": spent,
            "last_run_utc": _iso(),
            "note": ("units are charged BEFORE the call. A request that times "
                     "out still spent its quota at the provider."),
        })
        out["calls"] += 1
        out["searches"] += 1
        try:
            status, payload = _youtube_call(youtube_search_url(q), fetch=fetch)
        except Exception as exc:                                   # noqa: BLE001
            out["failures"].append(f"{q}: {type(exc).__name__}: {exc}")
            continue
        if status != 200 or not isinstance(payload, dict):
            out["failures"].append(f"{q}: HTTP {status} (403 here is usually quota)")
            continue
        for item in payload.get("items") or []:
            vid = str(((item.get("id") or {}) if isinstance(item, dict) else {})
                      .get("videoId") or "")
            snip = (item.get("snippet") or {}) if isinstance(item, dict) else {}
            if not vid or vid in known:
                out["dupes"] += 1
                continue
            rows.append(_row(
                source="youtube", kind="video", rid=vid, parent_id="",
                channel=str(snip.get("channelTitle") or snip.get("channelId") or ""),
                author=str(snip.get("channelTitle") or ""),
                title=str(snip.get("title") or ""),
                text=str(snip.get("description") or ""),
                url=f"https://www.youtube.com/watch?v={vid}",
                created=str(snip.get("publishedAt") or ""),
                # search.list carries NO view or like count. An engagement
                # block invented here would be a zero that reads as a measured
                # zero; `videos.list` is what has them and is not this chunk.
                engagement={"query": q},
                tbl=tbl))

    out["rows"] = len(rows)
    out["written"] = _append("youtube", rows) if rows else {}
    out["rows_with_a_ticker"] = sum(1 for r in rows if r["ticker_mentions"])
    out["quota"]["units_spent_after"] = spent
    out["quota"]["searches_left_after"] = max(0, (cap - spent) // unit_cost)
    out["wall_s"] = round(time.time() - t0, 1)
    if out["refused"] and not rows:
        out["status"] = "REFUSED"
    out["headline"] = (f"{out['searches']} search(es), {len(rows)} new video(s), "
                       f"{spent}/{cap} units spent on {day} (Pacific)")
    return out


def transcript_refusal() -> dict:
    """Why no transcript is pulled here. A NAME, not a silence."""
    return {
        "refused": "TRANSCRIPT_SOURCE_NOT_LAWFUL_HERE",
        "why": (
            "`youtube-transcript-api` has no ToS grant (it works because "
            "YouTube's caption endpoint is unauthenticated), and per the spec's "
            "own source table cloud-provider IPs are actively blocked in 2026 — "
            "the configuration that works is a rotating residential proxy at "
            "$20-50/mo. Neither the permission nor the proxy exists, so the "
            "step is refused BY NAME rather than attempted and silently "
            "failing, which would look exactly like a dead feed."),
        "what_would_change_it": (
            "a lawful transcript source (the spec's §1 candidates: SEC 8-K "
            "Ex.99 — already built in chunk 20 T1 — company IR pages one "
            "domain at a time, or a paid vendor after its ToS is read), or a "
            "decision to buy a residential proxy with that decision written "
            "down"),
    }


# -------------------------------------------------------------------- the run

def pull(*, sources: tuple[str, ...] = SOURCES, dry_run: bool = False,
         client=None, fetch: Callable[[str], tuple[int, bytes]] | None = None,
         pace_s: float = PACE_S, budget_s: float = 0.0,
         posts_per_sub: int | None = None) -> dict:
    """Every named source, each with its own block on ONE receipt."""
    t0 = time.time()
    unknown = [s for s in sources if s not in SOURCES]
    if unknown:
        raise SocialRefused(
            f"UNKNOWN_SOURCE: {', '.join(unknown)} — this collector knows "
            f"{list(SOURCES)}. A source not named here cannot be pulled.")
    per: list[dict] = []
    for s in sources:
        if s == "reddit":
            per.append(pull_reddit(client=client, dry_run=dry_run, pace_s=pace_s,
                                   budget_s=budget_s, posts_per_sub=posts_per_sub))
        else:
            per.append(pull_youtube(fetch=fetch, dry_run=dry_run, pace_s=pace_s))

    refusals = {p["source"]: p["refused"] for p in per if p.get("refused")}
    receipt = {
        "job": JOB, "licence": LICENCE, "llm_spend_usd": 0.0,
        "dry_run": bool(dry_run),
        "sources": list(sources),
        "rows_new": sum(int(p.get("rows") or 0) for p in per),
        "refusals": refusals,
        "refusal_names_declared": list(REFUSALS),
        "key_names_looked_for": {"reddit": list(REDDIT_KEY_NAMES),
                                 "youtube": list(YOUTUBE_KEY_NAMES)},
        "keys_present": key_status(),
        "per_source": per,
        "not_built": {
            "x_twitter": ("pay-per-read ($0.005/read, capped 2M/mo); OFF the "
                          "lab's automatic cadence by spec §4.3 and absent "
                          "from this file on purpose"),
            "instagram": ("no lawful path for this use case (spec §1) — do not "
                          "build a collector"),
            "stocktwits": "terms UNVERIFIED; needs a live probe before a parser",
            "transcripts": transcript_refusal()["refused"],
        },
        "pit_rule": (
            "first_seen_utc is THIS collector's clock. Every row is "
            "pit_grade index_state and may NEVER label a return: a platform "
            "can edit or delete a post or comment after the fact and we cannot "
            "detect the backfill (invariant 20)."),
        "engagement_rule": (
            "engagement is AS-OF FIRST SEEN and is never re-fetched. A "
            "later-fetched upvote count is itself a look-ahead."),
        "dir": str(social_dir()),
        "wall_s": round(time.time() - t0, 1),
        "written_utc": _iso(),
    }
    receipt["headline"] = (
        f"{receipt['rows_new']:,} new social row(s) over {len(sources)} source(s); "
        f"{len(refusals)} refused ({', '.join(sorted(refusals.values())) or 'none'})")
    if not dry_run:
        _write_json(receipt_path(_now().strftime("%Y%m%dT%H%M%SZ")), receipt)
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", default="all",
                    help=f"one of {list(SOURCES)}, or 'all'")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and the quota; make no request")
    ap.add_argument("--pace", type=float, default=PACE_S,
                    help="seconds between calls to one provider")
    ap.add_argument("--budget-s", type=float, default=0.0,
                    help="wall-clock budget for the Reddit sweep; 0 disables")
    ap.add_argument("--posts-per-sub", type=int, default=None,
                    help="override config.SOCIAL_REDDIT_POSTS_PER_SUB")
    a = ap.parse_args(argv)
    sources = SOURCES if a.source == "all" else (a.source,)
    try:
        out = pull(sources=tuple(sources), dry_run=a.dry_run, pace_s=a.pace,
                   budget_s=a.budget_s, posts_per_sub=a.posts_per_sub)
    except SocialRefused as exc:
        # A refusal about the INVOCATION is a fact about the command, so it is
        # the one non-zero exit. A refusal about the ENVIRONMENT (no key) is on
        # the receipt and exits 0.
        print(json.dumps({"job": JOB, "refused": str(exc)}, indent=1))
        return 2
    print(json.dumps(out, indent=1, default=str))
    return 0


__all__ = ["CASHTAG_RE", "JOB", "REDDIT_KEY_NAMES", "REFUSALS", "ROW_KEYS",
           "SOURCES", "SUBREDDITS", "SocialRefused", "YOUTUBE_KEY_NAMES",
           "YOUTUBE_QUERIES", "cashtag_count", "cursor_path", "key_status",
           "main", "missing_keys", "pull", "pull_reddit", "pull_youtube",
           "quota_day", "receipt_path", "reddit_client", "rows_path",
           "seen_ids", "social_dir", "ticker_mentions", "transcript_refusal",
           "youtube_search_url"]


if __name__ == "__main__":
    raise SystemExit(main())
