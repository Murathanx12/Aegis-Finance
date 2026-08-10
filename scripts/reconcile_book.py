"""Recover Murat's book from the sources the repo already holds.

    python scripts/reconcile_book.py                  # report only
    python scripts/reconcile_book.py --snapshot       # refresh the prod log first
    python scripts/reconcile_book.py --write-book     # rewrite murat_book.yaml
    python scripts/reconcile_book.py --write-doc      # docs/PORTFOLIO_RECONCILIATION.md

`--write-book` NEVER sets `confirmed: true`. Recovering share counts is not the
same as confirming a book: cash is unrecoverable from every source, and a NAV
missing its cash leg is not a NAV. The watermark stays until Murat says so.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services import pm_reconcile as R  # noqa: E402

DOC = Path(__file__).resolve().parents[1] / "docs" / "PORTFOLIO_RECONCILIATION.md"
JSON_OUT = Path(__file__).resolve().parents[1] / "docs" / "portfolio_reconciliation.json"


def snapshot_conviction(timeout: int = 90) -> dict:
    """Re-pull the immutable decision log from prod and cache it verbatim."""
    raw = urllib.request.urlopen(R.PROD_DECISIONS_URL, timeout=timeout).read()
    payload = json.loads(raw)
    snap = {
        "source": R.PROD_DECISIONS_URL,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "payload_sha256": hashlib.sha256(raw).hexdigest(),
        "note": ("READ-ONLY snapshot of the immutable conviction decision log on "
                 "prod. Cached so the reconciler is reproducible offline; prod "
                 "remains authoritative."),
        "decisions": payload["decisions"],
    }
    R.CONVICTION_SNAPSHOT.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap


def render_doc(rep: dict) -> str:
    s = rep["summary"]
    L: list[str] = []
    add = L.append
    add("# Portfolio reconciliation — what the repo already knew")
    add("")
    add(f"_Generated {rep['generated_at']} by `scripts/reconcile_book.py`._")
    add("")
    add("BUILD-1.1 finished by asking Murat to type in his holdings. He answered:")
    add("*\"mirror and conviction is already my portfolio, i logged them.\"* He was")
    add("right. Three sources in this repo carried the book and nothing had ever")
    add("read two of them together. This is what they say, including where they")
    add("disagree.")
    add("")
    add("## Sources")
    add("")
    add("| source | status | what it is |")
    add("|---|---|---|")
    for k, v in rep["sources"].items():
        add(f"| `{k}` | {v.get('status')} | {v.get('note','')} |")
    add("")
    conv = rep["sources"].get("conviction_log", {})
    if conv.get("payload_sha256"):
        add(f"Conviction log payload SHA-256 `{conv['payload_sha256'][:32]}…`, "
            f"fetched {conv.get('logged_at')}.")
        add("")
    add("## The recovered book")
    add("")
    add(f"**{s['n_positions_recovered']} positions, all {s['n_share_counts_known']} "
        f"share counts recovered.** {s['n_contested']} contested. Cost basis: "
        f"{s['n_cost_basis_reconstructed']} reconstructed, "
        f"{s['n_cost_basis_missing']} missing. Cash: **{s['cash']}**.")
    add("")
    add("| ticker | shares | source | contested | cost basis | basis status |")
    add("|---|---:|---|---|---:|---|")
    for p in rep["positions"]:
        cb = "—" if p["cost_basis"] is None else f"{p['cost_basis']:g}"
        add(f"| {p['ticker']} | {p['shares']:g} | {p['shares_source']} | "
            f"{'**YES**' if p['shares_contested'] else 'no'} | {cb} | "
            f"{p['cost_basis_status']} |")
    add("")
    add("## Disagreements — printed, not resolved")
    add("")
    if not rep["disagreements"]:
        add("None.")
    for d in rep["disagreements"]:
        if d["kind"] == "share_count":
            claims = ", ".join(f"`{k}` = {v:g}" for k, v in d["claims"].items())
            add(f"* **{d['ticker']} share count.** {claims}. Using "
                f"**{d['using']['value']:g}** from `{d['using']['source']}` — "
                f"{d['why']}. **Murat should confirm which is right.**")
        else:
            add(f"* **{d['kind']}**: {d.get('detail')}")
    add("")
    add("## What is genuinely unrecoverable")
    add("")
    for u in rep["unrecoverable"]:
        if u["field"] == "cash":
            add(f"* **cash** — {u['why']}")
    missing = [u["ticker"] for u in rep["unrecoverable"]
               if u["field"] == "cost_basis"]
    if missing:
        add(f"* **cost basis for {len(missing)} names** ({', '.join(missing)}) — "
            "no source carries a fill price. The conviction log's `price` is the "
            "market price on 2026-07-11, the day the decisions were typed in, "
            "and the rationale says the shares were bought months earlier. "
            "Using it as a cost basis would silently invent a P&L.")
    add("")
    add("## Excluded — in the January reconstruction, not in the book")
    add("")
    add("The conviction log enumerates the whole book as of 2026-07-11. A name in")
    add("the January PDF but absent from that log is read as **exited**. This is")
    add("the one inference in this document rather than a reading, so it is")
    add("flagged for confirmation.")
    add("")
    add("| ticker | reconstruction cost basis |")
    add("|---|---:|")
    seen = set()
    for e in rep["excluded"]:
        if e["ticker"] in seen:
            continue
        seen.add(e["ticker"])
        cb = e.get("reconstruction_cost_basis")
        add(f"| {e['ticker']} | {'—' if cb is None else f'{cb:g}'} |")
    add("")
    add("## What is still needed from Murat")
    add("")
    add("Two fields, and only two:")
    add("")
    add("1. **`cash`** — the brokerage cash balance. Without it the NAV is the")
    add("   equity value only, and every weight is computed against the wrong")
    add("   denominator.")
    add("2. **QUBT: 300 or 200 shares?** The dated log says 300; the lane config")
    add("   says 200.")
    add("")
    add("Optional but useful: fill prices for "
        f"{', '.join(missing) if missing else 'the names above'} — without them")
    add("the book has no P&L for those positions, though every forward-looking")
    add("number works fine, because cost basis does not enter a decision.")
    add("")
    add("Until `cash` is supplied the book stays `confirmed: false` and every")
    add("dollar figure prints **SIMULATED — DO NOT EXECUTE**.")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true",
                    help="re-pull the conviction log from prod first")
    ap.add_argument("--write-book", action="store_true")
    ap.add_argument("--write-doc", action="store_true")
    ap.add_argument("--cash", type=float, default=0.0)
    args = ap.parse_args()

    if args.snapshot:
        try:
            snap = snapshot_conviction()
            print(f"[snapshot] {len(snap['decisions'])} decisions, "
                  f"sha {snap['payload_sha256'][:16]}")
        except Exception as exc:  # noqa: BLE001 - report, then use the cache
            print(f"[snapshot] FAILED ({type(exc).__name__}: {exc}) — "
                  f"falling back to the cached snapshot, which is dated in the "
                  f"report so nobody mistakes it for live")

    rep = R.reconcile()
    s = rep["summary"]
    print(json.dumps(s, indent=2))
    for p in rep["positions"]:
        flag = " CONTESTED" if p["shares_contested"] else ""
        print(f"  {p['ticker']:6} {p['shares']:>8g} via {p['shares_source']:15}"
              f" basis={p['cost_basis_status']}{flag}")
    for d in rep["disagreements"]:
        print(f"  ! {d['kind']}: {d.get('ticker','')} {d.get('claims', d.get('detail'))}")

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"\nwrote {JSON_OUT}")

    if args.write_doc:
        DOC.write_text(render_doc(rep), encoding="utf-8")
        print(f"wrote {DOC}")

    if args.write_book:
        mb = R.read_murat_book()
        text = R.to_book_yaml(
            rep, confirmed=False, cash=args.cash,
            sizing_mode=mb.get("sizing_mode", "high_growth"),
            wealth_targets=mb.get("wealth_targets"),
            watchlist=mb.get("watchlist"))
        R.MURAT_BOOK.write_text(text, encoding="utf-8")
        print(f"wrote {R.MURAT_BOOK} (confirmed: false — cash is still unknown)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
