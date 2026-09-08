"""Pull GDELT's 15-minute whole-market feed into the resumable raw store.

    python -m scripts.gdelt_pull --minutes 120 --streams export,mentions
    python -m scripts.gdelt_pull --start 20260907000000 --end 20260907030000
    python -m scripts.gdelt_pull --status          # where did the last run stop?

WHY GDELT AND WHY RAW
=====================
Roadmap E4 and VISION §4.1: GDELT is the **whole-market, Asia-first** layer --
events plus GKG, every 15 minutes, 100+ languages, free. It is the DENOMINATOR
for coverage normalisation. A signal built on English-language US wires cannot
tell "nothing happened" from "nothing we subscribe to reported it", and that
distinction is the difference between a news feature and a coverage feature.

The zips are stored EXACTLY as they came off the wire. Parsing GDELT's 61-column
CSV is a downstream step that must be re-runnable without re-fetching, because a
re-fetch of a 15-minute window is not available at all: GDELT keeps the files,
but the articles they point at expire, get paywalled and get edited.

WHAT THIS DOES NOT TOUCH
========================
Alpaca and Finnhub news. Another lane owns that leg (roadmap E1/E2) and two
pullers writing one store is how a cursor ends up describing somebody else's
progress.

RESUME IS THE POINT
===================
The previous news pull died at 112/134 months -- 83.6% -- with no cursor, no log
and no partial receipt, so all of it was redone. Here the cursor is written after
each stamp completes, the log is a file, the pid is on disk, and the coverage
receipt is rewritten every `--receipt-every` documents. Kill this at any moment
and rerun the identical command: it starts at the next stamp.

ROBOTS AND RATE
===============
`robots.txt` is fetched and honoured before the first request. On 2026-09-07 both
`data.gdeltproject.org` and `api.gdeltproject.org` return 404 for it -- no file
means nothing is disallowed, which is a DIFFERENT fact from "we did not check",
and the log records which of the two happened. Requests are spaced by `--sleep`
(default 1.0 s) and carry a descriptive, contactable User-Agent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.robotparser import RobotFileParser

from backend.services.scrape_store import USER_AGENT, ScrapeStore

SOURCE = "gdelt_v2"
BASE = "http://data.gdeltproject.org/gdeltv2"
LASTUPDATE = f"{BASE}/lastupdate.txt"
STREAMS = {"export": "export.CSV.zip",
           "mentions": "mentions.CSV.zip",
           "gkg": "gkg.csv.zip"}
STAMP = "%Y%m%d%H%M%S"


def _get(url: str, timeout: int = 90) -> tuple[int, bytes]:
    """Fetch, returning (status, body). A non-200 is DATA, not an exception.

    A 404 for a 15-minute stamp means GDELT published nothing for that window,
    which is a coverage fact worth storing. A store that keeps only successes
    cannot tell "we looked and it was not there" from "we never looked".
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() or b""


def robots_verdict(host_url: str) -> dict:
    """Three outcomes, never two: allowed / disallowed / no file at all."""
    rp = RobotFileParser()
    robots_url = host_url.rstrip("/") + "/robots.txt"
    status, body = _get(robots_url, timeout=30)
    if status != 200:
        return {"robots": "ABSENT", "http": status, "allowed": True,
                "why": f"{robots_url} returned {status}; no file means nothing "
                       "is disallowed -- which is not the same fact as 'we did "
                       "not check', and this line is the difference"}
    rp.parse(body.decode("utf-8", "replace").splitlines())
    allowed = rp.can_fetch(USER_AGENT, host_url + "/gdeltv2/")
    return {"robots": "PRESENT", "http": 200, "allowed": bool(allowed),
            "why": f"robots.txt parsed; can_fetch({host_url}/gdeltv2/)={allowed}"}


def last_update() -> dict:
    """The three newest files, with GDELT's own size and MD5 for each.

    The MD5 is why this is fetched even when a range is given: it is an
    INDEPENDENT checksum of the body, so a truncated download is caught at store
    time rather than by a parser three weeks later.
    """
    status, body = _get(LASTUPDATE, timeout=30)
    out = {"http": status, "files": {}, "stamp": None}
    if status != 200:
        return out
    for line in body.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        size, md5, url = parts
        name = url.rsplit("/", 1)[-1]
        stamp = name.split(".", 1)[0]
        out["stamp"] = stamp
        out["files"][name] = {"n_bytes": int(size), "md5": md5, "url": url}
    return out


def stamps(start: datetime, end: datetime):
    """Every 15-minute stamp in [start, end], inclusive, snapped to the grid."""
    t = start.replace(second=0, microsecond=0)
    t -= timedelta(minutes=t.minute % 15)
    while t <= end:
        yield t.strftime(STAMP)
        t += timedelta(minutes=15)


def _parse_when(s: str) -> datetime:
    s = s.strip()
    for fmt in (STAMP, "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def run(args) -> int:
    store = ScrapeStore(SOURCE)
    if args.status:
        rec = store.receipt(write=False)
        print(json.dumps(rec, indent=1))
        return 0

    store.begin(argv=sys.argv[1:])
    verdict = robots_verdict("http://data.gdeltproject.org")
    store.log(f"ROBOTS {verdict['robots']} allowed={verdict['allowed']} "
              f"({verdict['why']})")
    if not verdict["allowed"]:
        store.log("REFUSE robots.txt disallows this path")
        store.finish(note="refused by robots.txt")
        return 2

    lu = last_update()
    store.log(f"LASTUPDATE http={lu['http']} stamp={lu['stamp']} "
              f"files={len(lu['files'])}")
    md5s = {name: v["md5"] for name, v in lu["files"].items()}

    newest = (_parse_when(lu["stamp"]) if lu["stamp"]
              else datetime.now(timezone.utc))
    if args.start:
        start, end = _parse_when(args.start), (
            _parse_when(args.end) if args.end else newest)
    else:
        start, end = newest - timedelta(minutes=args.minutes), newest

    # THE RESUME. The cursor is the last stamp that COMPLETED, so the next run
    # begins one grid step after it. Re-running the identical command is the
    # resume -- there is no separate --resume flag to forget.
    # ONE CURSOR PER TRAVERSAL. `--start/--end` is a backfill of a named window;
    # the default rolling mode is the "tail". They are different traversals and
    # must not share a position -- on the first pass they did, and a backfill of
    # 04:00-08:00 fast-forwarded itself to 10:00 on the tail's cursor, fetched
    # ZERO stamps and reported success. A cursor that skips work while reporting
    # success is the exact failure this store exists to prevent.
    ckey = (f"window:{start.strftime(STAMP)}-{end.strftime(STAMP)}"
            if args.start else "tail")
    cur = store.cursor(ckey)
    if cur and not args.restart:
        cur_t = _parse_when(cur)
        if start <= cur_t <= end:
            start = cur_t + timedelta(minutes=15)
            store.log(f"RESUME {ckey} cursor={cur} -> starting at "
                      f"{start.strftime(STAMP)}")
        else:
            store.log(f"CURSOR {ckey}={cur} is outside "
                      f"[{start.strftime(STAMP)}..{end.strftime(STAMP)}] -- "
                      "ignored; store.has() still dedupes every document.")

    streams = [s.strip() for s in args.streams.split(",") if s.strip()]
    for s in streams:
        if s not in STREAMS:
            store.log(f"REFUSE unknown stream {s!r}; have {sorted(STREAMS)}")
            store.finish(note="unknown stream")
            return 2

    todo = list(stamps(start, end))
    store.log(f"PLAN {len(todo)} stamps x {len(streams)} streams "
              f"[{start.strftime(STAMP)} .. {end.strftime(STAMP)}] "
              f"limit={args.limit}")
    n_new = n_skip = n_fail = 0
    for stamp in todo:
        if args.limit and n_new >= args.limit:
            store.log(f"STOP --limit {args.limit} reached")
            break
        ok_this_stamp = True
        for s in streams:
            name = f"{stamp}.{STREAMS[s]}"
            url = f"{BASE}/{name}"
            if store.has(url):
                n_skip += 1
                continue
            status, body = _get(url, timeout=args.timeout)
            got = hashlib.md5(body).hexdigest() if body else ""
            expect = md5s.get(name)
            # An MD5 we can check and that does NOT match is a truncated body.
            # It is stored anyway, flagged, and counted -- deleting it would
            # hide the fact that this window needs re-fetching.
            mismatch = bool(expect and got and expect != got)
            store.put(url, status, body, cursor=stamp,
                      meta={"stream": s, "stamp": stamp, "md5": got,
                            "md5_expected": expect,
                            "md5_mismatch": mismatch})
            if status == 200 and not mismatch:
                n_new += 1
            else:
                n_fail += 1
                ok_this_stamp = False
                store.log(f"FAIL {name} http={status} bytes={len(body)} "
                          f"md5_mismatch={mismatch}")
            time.sleep(args.sleep)
        # CURSOR AFTER THE DATA, and only when the whole stamp landed. A cursor
        # ahead of its bodies skips work silently on the next run; re-doing a
        # stamp is cheap and visible, missing one is neither.
        if ok_this_stamp:
            store.advance(stamp, key=ckey)
        if (n_new + n_skip + n_fail) % args.receipt_every == 0:
            store.receipt(note="in flight")
    rec = store.finish(note=f"new={n_new} skipped={n_skip} failed={n_fail}")
    print(json.dumps({"new": n_new, "skipped": n_skip, "failed": n_fail,
                      "cursors": rec["cursors"], "n_docs": rec["n_docs"],
                      "n_bytes": rec["n_bytes"],
                      "receipt": str(store.receipt_path)}, indent=1))
    return 0


def main() -> int:
    import backend.config  # noqa: F401  gated dotenv load, for consistency

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--minutes", type=int, default=60,
                   help="how far back from the newest published stamp")
    p.add_argument("--start", help="YYYYMMDDHHMMSS (overrides --minutes)")
    p.add_argument("--end", help="YYYYMMDDHHMMSS; defaults to newest")
    p.add_argument("--streams", default="export,mentions",
                   help="export,mentions,gkg  (gkg is ~4.5 MB per stamp)")
    p.add_argument("--limit", type=int, default=0,
                   help="stop after N NEW documents (0 = no limit)")
    p.add_argument("--sleep", type=float, default=1.0)
    p.add_argument("--timeout", type=int, default=90)
    p.add_argument("--receipt-every", type=int, default=5)
    p.add_argument("--restart", action="store_true",
                   help="ignore the cursor (does NOT delete anything)")
    p.add_argument("--status", action="store_true",
                   help="print where the last run stopped and exit")
    return run(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
