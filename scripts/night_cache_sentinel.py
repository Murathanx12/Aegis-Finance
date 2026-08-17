"""Read-only sentinel for the stale-history hazard on the night's read path.

    python -m scripts.night_cache_sentinel --before
    python -m scripts.night_cache_sentinel --log run.log

NOT ON THE NIGHT'S CRITICAL PATH. It imports `backend.cache` to PEEK and reads
a text file. It writes nothing, edits nothing, and the night does not call it.

WHY IT EXISTS RATHER THAN A TYPED GREP
======================================
Order 11's addendum is right that `fetch_ticker_history` can serve a copy up to
`_STALE_OK = 24h` old with the same shape as a fresh one, and that the only
trace is a `logger.warning`. Checking the log for it is the right instinct. But
the patterns it named do not cover the path, in three ways, and a check whose
pattern matches nothing is a check that never fires:

1. **`RateLimited` is never logged.** It is an exception class raised at
   data_fetcher.py:100 and :113 and never caught-and-logged by name. Grepping a
   run log for "RateLimited" finds it only if it escaped as an unhandled
   traceback — i.e. only in the case where the night already crashed and you did
   not need a grep to notice.

2. **The stale serve is SILENT for every ticker after the first.** Only the one
   that catches the 429 logs `serving stale history`. Once `_trip_rl_breaker()`
   fires, `_rl_breaker_active()` short-circuits at data_fetcher.py:97-101 and
   returns the stale copy with NO log line at all. So `serving stale history`
   under-counts by however many names follow within the 90s cooldown, which on a
   40-name assembly is most of them.

   What IS always logged when the breaker trips is
   `Yahoo rate limit hit — pausing all yfinance calls for Ns`, and the breaker
   is the only gate to the silent branch. That line, not the stale one, is the
   complete in-process sentinel.

3. **The breaker key is written through to DISK** (`cache_set` -> `_disk_set`),
   so it survives the process that set it. A breaker tripped by an earlier local
   process inside its 90s window makes `_rl_breaker_active()` true in the
   night's process with NOTHING in the night's own log. That is the one case
   both greps miss, and it is exactly the hazard rule 2 exists for. `--before`
   closes it by peeking at the key before the run starts.

THE PART THAT WOULD HAVE MADE A HAND-ROLLED CHECK HARMFUL
=========================================================
`cache_get` DELETES the disk entry when it is past the TTL you pass
(`_disk_get` -> `dc.delete(key)`). A pre-run check written as
`cache_get("yf:rate_limit_breaker", 90)` — or worse, a poke at
`cache_get("tkr:hist10y:AAPL", 900)` to "see if it's warm" — evicts the very
stale copies the night would fall back on. This peeks and only peeks.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: Lines that mean the snapshot may contain day-old history stamped as fresh.
ABORT_PATTERNS = (
    # Always emitted when the breaker trips; every silent stale serve is behind
    # it, so this is the one that must be present in the check.
    "Yahoo rate limit hit",
    # The first stale serve. Kept because it names the ticker.
    "serving stale history",
)

#: Not a staleness hazard — a COVERAGE one. The name returns None and drops out
#: of the snapshot quietly, which changes what the arms were shown.
WARN_PATTERNS = ("history fetch failed",)

BREAKER_KEY = "yf:rate_limit_breaker"
BREAKER_COOLDOWN = 90


def before() -> int:
    """Is a rate-limit breaker already hot from an earlier process?"""
    from backend.cache import cache_peek           # peek, never get

    value, age = cache_peek(BREAKER_KEY, BREAKER_COOLDOWN)
    if value is None:
        print("OK  no rate-limit breaker set — Yahoo will be attempted for real")
        return 0
    print(f"ABORT  a rate-limit breaker is ALREADY ACTIVE ({age:.0f}s old, "
          f"cooldown {BREAKER_COOLDOWN}s).")
    print("       Every history read in this window returns a stale copy with")
    print("       NO log line, so the run log will look clean. Wait for it to")
    print(f"       expire ({BREAKER_COOLDOWN - (age or 0):.0f}s) and re-check.")
    return 1


def scan(path: Path) -> int:
    if not path.exists():
        print(f"REFUSE  {path} does not exist. This check reads a captured run")
        print("        log; the night logs to stderr and installs no file")
        print("        handler, so the run has to be TEED for there to be")
        print("        anything to scan. A check that cannot see its input is")
        print("        not a check that passed.")
        return 2
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print(f"REFUSE  {path} is empty — nothing was captured.")
        return 2

    lines = text.splitlines()
    hits = {p: [ln for ln in lines if p in ln] for p in ABORT_PATTERNS}
    warns = {p: [ln for ln in lines if p in ln] for p in WARN_PATTERNS}
    n_abort = sum(len(v) for v in hits.values())

    print(f"scanned {len(lines)} lines of {path}")
    for p, v in hits.items():
        print(f"  {'HIT ' if v else 'none'}  {p!r}  x{len(v)}")
        for ln in v[:5]:
            print(f"        {ln.strip()[:110]}")
    for p, v in warns.items():
        if v:
            print(f"  WARN  {p!r} x{len(v)} — those names dropped OUT of the "
                  f"snapshot rather than going stale")

    if n_abort:
        print("\nABORT. At least one history read was served from cache while")
        print("Yahoo was throttling. `iif1_features` stamps fetched_at = now and")
        print("`assert_decision_time_fresh` compares decision_ts to the wall")
        print("clock, not to the age of the data, so the guard passes on a")
        print("day-stale snapshot. Re-freeze and restart; the 17:00 start is")
        print("what makes that affordable.")
        return 1
    print("\nOK. No stale-serve and no breaker trip in this log.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", action="store_true",
                    help="pre-run: is a breaker already hot from another process?")
    ap.add_argument("--log", type=Path, help="post-assembly: scan a captured log")
    a = ap.parse_args()
    if a.before:
        return before()
    if a.log:
        return scan(a.log)
    ap.error("pass --before or --log")


if __name__ == "__main__":
    raise SystemExit(main())
