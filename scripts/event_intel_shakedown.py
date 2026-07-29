"""EVENT-INTEL pre-deploy shakedown (2026-07-29B acceptance spec).

Runs the extractor over the real watchlist feeds, validates the structure of
every emitted event, and prints a 50-event sample for manual audit.
Acceptance: >=90% of a 100-item sample parse to valid structure or land in
FAILED honestly; forbidden language count must be 0.

Usage (network required):
    python scripts/event_intel_shakedown.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import config
from backend.services import event_intel as ei

_ALLOWED_TIERS = {"HIGH", "MEDIUM", "LOW", "FAILED"}
_ALLOWED_BASES = {"EXPLICIT", "IMPLIED", "NEUTRAL", "UNKNOWN"}


def valid_structure(ev: dict) -> list[str]:
    """Return list of defects (empty = valid)."""
    defects = []
    if ev.get("event_type") not in ei._ALLOWED_EVENT_TYPES:
        defects.append(f"bad event_type {ev.get('event_type')}")
    if ev.get("direction") not in ei._ALLOWED_DIRECTIONS:
        defects.append(f"bad direction {ev.get('direction')}")
    if ev.get("direction_basis") not in _ALLOWED_BASES:
        defects.append(f"bad basis {ev.get('direction_basis')}")
    if ev.get("direction_relative_to") != ev.get("scope"):
        defects.append("direction not relative to scope")
    if (ev.get("extraction") or {}).get("tier") not in _ALLOWED_TIERS:
        defects.append("bad tier")
    if not (ev.get("source") or {}).get("feed"):
        defects.append("missing source.feed")
    if not ev.get("title"):
        defects.append("empty title")
    if ei._FORBIDDEN_RE.search(ev.get("title") or ""):
        defects.append(f"FORBIDDEN LANGUAGE: {ev['title']}")
    br = (ev.get("context") or {}).get("base_rate") or {}
    if br.get("status") == "measured" and "n" not in br:
        defects.append("measured base rate without N")
    return defects


def main() -> int:
    tickers = config["stock_universe"]["default_watchlist"][:30]
    all_events, defects_log, feed_fail = [], [], {}

    for i, t in enumerate(tickers):
        out = ei.get_ticker_events(t)
        for f in out["unavailable_feeds"]:
            feed_fail[f] = feed_fail.get(f, 0) + 1
        for ev in out["events"]:
            d = valid_structure(ev)
            all_events.append(ev)
            if d:
                defects_log.append({"ticker": t, "defects": d, "title": ev.get("title")})
        print(f"[{i+1}/{len(tickers)}] {t}: {len(out['events'])} events, "
              f"unavailable={out['unavailable_feeds']}")

    n = len(all_events)
    n_bad = len(defects_log)
    sample = all_events[:100]
    sample_bad = sum(1 for ev in sample if valid_structure(ev))
    rate = (len(sample) - sample_bad) / len(sample) if sample else 0.0

    tiers, dirs, methods, feeds = {}, {}, {}, {}
    for ev in all_events:
        tiers[ev["extraction"]["tier"]] = tiers.get(ev["extraction"]["tier"], 0) + 1
        dirs[ev["direction"]] = dirs.get(ev["direction"], 0) + 1
        methods[ev["extraction"]["method"]] = methods.get(ev["extraction"]["method"], 0) + 1
        feeds[ev["source"]["feed"]] = feeds.get(ev["source"]["feed"], 0) + 1

    print("\n===== SHAKEDOWN SUMMARY =====")
    print(f"tickers: {len(tickers)}  events: {n}  structural defects: {n_bad}")
    print(f"valid-structure rate on {len(sample)}-item sample: {rate:.1%} (bar 90%)")
    print(f"tiers: {tiers}\ndirections: {dirs}\nmethods: {methods}\nfeeds: {feeds}")
    print(f"feed unavailable counts: {feed_fail}")
    if defects_log:
        print("\nDEFECTS:")
        for d in defects_log[:20]:
            print(json.dumps(d))

    print("\n===== 50-EVENT MANUAL AUDIT SAMPLE =====")
    for ev in all_events[:50]:
        print(f"{ev['scope']:6} {ev['source']['feed']:14} "
              f"{ev['event_type']:18} {ev['direction']:8} "
              f"{ev['direction_basis']:8} {ev['extraction']['tier']:6} "
              f"| {ev['title'][:90]}")

    print(f"\nVERDICT: {'PASS' if rate >= 0.90 and not any('FORBIDDEN' in str(d) for d in defects_log) else 'FAIL'}")
    return 0 if rate >= 0.90 else 1


if __name__ == "__main__":
    sys.exit(main())
