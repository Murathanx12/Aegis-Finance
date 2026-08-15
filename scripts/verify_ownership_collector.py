"""Did the ownership collector actually work IN PRODUCTION?

    python -m scripts.verify_ownership_collector

WHY THIS IS A SCRIPT AND NOT A GLANCE AT A LOG
==============================================
This project has already shipped a collector that passed twelve offline tests
while 403-ing on 100% of its production fetches (T9, 2026-06-17). It ran green,
it logged, and every dashboard read "covered". A local success proves the
parser; it proves nothing about whether Railway's egress can reach EDGAR.

So the only acceptable evidence is the DURABLE RECEIPT, read back through the
production API. This script fetches it and answers, one line each, the twelve
questions the brain's order asks — plus the one that matters most, which is
whether the run has the T9 SHAPE: documents attempted, zero fetched.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

DEFAULT_BASE = "https://aegis-finance-production.up.railway.app"


def fetch(base: str, path: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(base.rstrip("/") + path,
                                 headers={"User-Agent": "aegis-verify/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default=DEFAULT_BASE)
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    try:
        health = fetch(a.base, "/api/health/full")
        print(f"deploy      {health.get('deploy', {}).get('commit', '?')[:8]}  "
              f"status {health.get('status')}")
    except Exception as exc:                                     # noqa: BLE001
        print(f"health      UNREACHABLE ({type(exc).__name__}: {exc})")

    body = fetch(a.base, "/api/optimus/job_receipts?limit=5")
    blk = body.get("pi_ownership_collect", {})

    print(f"\nreceipt dir {blk.get('dir')}")
    print(f"exists      {blk.get('exists')}   n_receipts "
          f"{blk.get('n_receipts')}")
    if not blk.get("exists") or not blk.get("receipts"):
        print(f"\nVERDICT     NO PRODUCTION RUN HAS WRITTEN A RECEIPT YET.")
        print(f"            {blk.get('note', '')}")
        print("            This is NOT a failure — it is the absence of "
              "evidence, and\n            the two must not be confused. The "
              "job runs 06:00 ET daily.")
        return 2

    r = blk["receipts"][0]
    if r.get("unreadable"):
        print(f"\nVERDICT     RECEIPT UNREADABLE: {r.get('error')}")
        return 1

    g = r.get
    print(f"\nday         {g('day')}      ran_at {g('ran_at')}")
    print(f"status      {g('source_status')}   {g('reason') or ''}")
    print("\n── the twelve ──")
    rows = [
        ("index rows", g("n_index_rows")),
        ("unique accessions", g("n_unique_accessions")),
        ("documents fetched", g("n_documents_fetched")),
        ("attempted", g("n_attempted")),
        ("coverage", g("coverage")),
        ("parse errors", g("n_parse_errors")),
        ("BUY", g("n_buys")),
        ("SELL", g("n_sells")),
        ("mechanical / other", g("n_mechanical")),
        ("distinct actors", g("n_distinct_actors")),
        ("distinct tickers", g("n_distinct_tickers")),
        ("fetch seconds", g("fetch_seconds")),
        ("total seconds", g("total_seconds")),
        ("events written", g("written")),
        ("duplicates skipped", g("duplicates")),
        ("usable events", g("usable_events")),
    ]
    for k, v in rows:
        mark = "  *** MISSING FROM RECEIPT" if v is None else ""
        print(f"  {k:<22s} {v}{mark}")
    print(f"  failure classes        {g('failure_classes')}")
    print(f"  events by action       {g('events_by_action')}")

    # ── the judgements ──────────────────────────────────────────────────────
    print("\n── verdict ──")
    attempted = g("n_attempted") or 0
    fetched = g("n_documents_fetched")
    written = g("written") or 0
    status = g("source_status")
    rc = 0

    if status == "NOT_YET_PUBLISHED":
        print("  EDGAR had not posted the index yet. Expected near the "
              "boundary; not a failure.")
    elif fetched is not None and attempted > 0 and fetched == 0:
        # The exact T9 shape, named.
        print("  *** T9 SHAPE: documents were attempted and ZERO were "
              "fetched.")
        print("      The collector ran, logged, and reached nothing. This is "
              "the failure\n      that once passed twelve tests. Check "
              "Railway egress and the SEC\n      User-Agent before trusting "
              "any downstream count.")
        rc = 1
    elif written == 0:
        print("  Ran and wrote NOTHING. That is either a genuinely quiet day "
              "or a dead\n  fetch path, and the two look identical on every "
              "dashboard — read\n  failure_classes above before calling it "
              "quiet.")
        rc = 1
    else:
        print(f"  Collector reached EDGAR from production: {fetched} "
              f"documents fetched,\n  {written} events written, "
              f"{g('n_distinct_actors')} actors, "
              f"{g('n_distinct_tickers')} tickers.")

    # Idempotency is only answerable across two runs, and the second is the
    # next scheduled one. Saying so beats printing a field nobody measured.
    if len(blk["receipts"]) >= 2:
        prev = blk["receipts"][1]
        print(f"  idempotency: previous run ({prev.get('day')}) wrote "
              f"{prev.get('written')} with {prev.get('duplicates')} "
              f"duplicates skipped")
    else:
        print("  idempotency: UNMEASURED — only one run exists. It is "
              "answerable on the\n  second run, by whether `duplicates` "
              "absorbs the overlap.")

    if written and not (g("n_sells") or 0) and (g("n_buys") or 0):
        print("  *** BUYS ONLY. The pre-2026-08 path kept purchases and would "
              "have made\n      the Teacher Library a collection of "
              "successful-looking buy stories.")
        rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
