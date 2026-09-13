"""B/B′ — the beta-matched twin the insider-cluster books never got (chunk 12, T4).

THE DEFECT, AND WHY IT WAS INVISIBLE
====================================
`paper_books.LONG_ONLY_RULES` is the tuple that decides which books are owed a
beta-matched twin, and on 2026-09-12 it read

    ("top_k", "composite_top_k", "threshold_coverage")

— a list of the construction rules that happened to exist when it was written.
Lane B's two insider-cluster books are the programme's only `passthrough` books,
so they were seeded with ONE twin where their own pre-registration names two,
and `seed_receipt.json` records exactly that: A, C and D carry a
`random_universe` AND a `beta_matched` twin; `insider_cluster_length_v1` and
`insider_cluster_same_day_v1` carry only the random one.

`passthrough` joined `LONG_ONLY_RULES` the same day, so every book created from
then on is owed both. What the fix does NOT do is go back: a book's id is its
contract's fingerprint, the contract already existed, and `seed_first_books`
correctly reports `created: false` and adds nothing. The twin has to be made by
a job that knows it is completing a control set rather than creating a book.

WHAT THIS SCRIPT DOES, AND WHAT IT REFUSES TO DO
================================================
It computes the gap and the membership, and it does not write. Specifically:

* it asks `make_twins` what each existing book is owed NOW, compares that with
  the kinds the book actually carries, and names the difference;
* for each missing kind it builds the twin THROUGH `paper_books.make_twins` —
  never through a second implementation — so the membership, the seed, the
  decile match and the `UNMATCHED` flag are the ones the real path produces;
* it writes a receipt with all of that and prints the attended command.

Writing is gated on `AEGIS_RESEED_BETA_TWINS=1`, which this script cannot set
and a session may not set for itself. Two reasons, and the second is the real
one:

1. adding a twin means writing the PARENT's row as well, because
   `control_twin_ids` lives there. That is a write into a seeded book's record,
   and "no mutation of seeded book histories" is one of the four things the
   three-licence note says never relaxes. Completing a control set is the benign
   case of that shape — and the way to keep it benign is that a human authorises
   it.
2. **the twin is DRAWN AT TODAY'S BARS.** A twin's `book_id` is the fingerprint
   of its contract and its contract carries its `symbols`, so the twin this
   script computes is not the twin the book would have had on 2026-09-12: it is
   matched on betas estimated over the 120 sessions ending today. That is
   defensible — the book has no NAV history either way — but it is a FACT about
   the control, it goes on the receipt, and it is not a session's call to make
   silently.

    python -m scripts.reseed_beta_twins                   # the plan, writes nothing
    python -m scripts.reseed_beta_twins --json
    AEGIS_RESEED_BETA_TWINS=1 python -m scripts.reseed_beta_twins --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger("reseed_beta_twins")

#: The flag a human sets. A session never sets it; `--apply` without it is a
#: refusal that prints the command rather than an error that hides it.
ARM_ENV = "AEGIS_RESEED_BETA_TWINS"

#: The two books this was written for, named so the receipt can say whether the
#: gap it found is the one that was expected. It is NOT a filter: the scan walks
#: every book, because a tuple of known cases is how `LONG_ONLY_RULES` went
#: wrong in the first place.
EXPECTED_GAP = ("insider_cluster_length_v1", "insider_cluster_same_day_v1")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def receipt_path(day: str | None = None) -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    day = day or datetime.now().strftime("%Y-%m-%d")
    d = OPTIMUS_LEDGER_DIR / f"night_factory_{day}"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"reseed_beta_twins_{day}.json"


def is_armed() -> bool:
    return os.environ.get(ARM_ENV, "").strip() == "1"


def twin_kind(book) -> str | None:
    """The `kind` a twin book declares, or None if it is not a twin."""
    return ((book.strategy.engine_params or {}).get("twin") or {}).get("kind")


def carried_kinds(book, *, conn=None) -> dict:
    """`{kind: book_id}` for the twins a parent actually carries on its row."""
    from backend.services import paper_books as PB

    out: dict = {}
    for tid in book.control_twin_ids:
        t = PB.get(tid, conn=conn)
        out[twin_kind(t) if t is not None else f"MISSING_ROW:{tid}"] = tid
    return out


def owed_kinds(book, *, bars=None, asof: date | None = None) -> list[str]:
    """Which twin kinds `make_twins` would produce for this book TODAY.

    Asked of the real function rather than re-derived from `LONG_ONLY_RULES`: a
    second reading of the rule is how the two come apart, and the gap this
    script exists to close was a tuple that had stopped matching the rules.
    """
    from backend.services import paper_books as PB

    built = PB.make_twins(book.strategy, cadence=book.cadence, bars=bars,
                          asof=asof)
    return [twin_kind(t) or "?" for t in built]


#: How many of a twin's names the receipt prints before it switches to a hash.
#: A `passthrough` parent's universe IS the liquidity band, so its beta-matched
#: twin carries thousands of symbols and two of those arrays would be most of
#: the receipt. The membership is still PINNED: `symbols_sha256` is over the
#: sorted list, so a later draw that differs by one name is visible.
SYMBOL_PREVIEW = 25

#: At or above this share of the parent's universe, a "beta-matched" draw is
#: reported as DEGENERATE: it handed back the band it was matching against.
DEGENERATE_COVERAGE = 0.95


def _twin_row(t, parent_symbols=()) -> dict:
    """One missing twin, with its membership pinned rather than dumped."""
    import hashlib

    params = t.strategy.engine_params or {}
    syms = list(params.get("symbols") or [])
    detail = params.get("twin") or {}
    # DEGENERATE = the "matched draw" gave back (almost) the parent's own
    # universe. Not an exact-set test: 10 of 2,834 names had no estimable beta
    # and were dropped from BOTH arms, so an equality check reads False on a
    # twin that is 99.6% the parent. The threshold is stated rather than implied.
    n_parent = len(set(parent_symbols))
    covered = (len(set(syms) & set(parent_symbols)) / n_parent) if n_parent else 0.0
    degenerate = bool(n_parent and set(syms) <= set(parent_symbols)
                      and covered >= DEGENERATE_COVERAGE)
    return {
        "degenerate_beta_match": degenerate,
        "degenerate_coverage_of_parent_universe": round(covered, 4),
        "parent_universe_size": n_parent,
        "degenerate_note": (
            f"MEASURED, and it is the finding of this scan: the parent is a "
            f"`passthrough` book whose universe IS the whole liquidity band, so "
            f"every beta decile's target count equals that decile's whole "
            f"membership and the 'matched draw' hands back the band. This twin "
            f"holds {len(syms)} of the parent's {n_parent} names "
            f"({covered:.1%}); the rest had no estimable beta and are dropped "
            f"from BOTH arms. The membership hash is therefore identical between "
            f"B and B'. It is still a real control -- equal-weight the band "
            f"against the signal's picks, which is exactly where a passthrough "
            f"book's edge has to come from -- but it is NOT beta-matched in any "
            f"informative sense: matching a universe's deciles to itself returns "
            f"the universe. Whether a control of that shape is worth adding is "
            f"part of what the attended step decides, and it is the reason this "
            f"script prints rather than writes."
            if degenerate else None),
        "kind": twin_kind(t), "book_id": t.book_id,
        "strategy_id": t.strategy.strategy_id,
        "n_symbols": len(syms),
        "symbols_preview": syms[:SYMBOL_PREVIEW],
        "symbols_sha256": hashlib.sha256(
            "\n".join(sorted(syms)).encode("utf-8")).hexdigest(),
        "twin_detail": detail,
        "matched": "UNMATCHED" not in detail,
        "universe_overlap_with_parent": detail.get("universe_overlap_with_parent"),
        "overlap_note": (
            "the parent is a `passthrough` book whose declared universe IS the "
            "liquidity band, so a draw from that band overlaps it entirely and "
            "this reads 1.0. That is not a broken control: it means the control "
            "does its work through the SIGNAL alone, which is what a "
            "beta-matched twin of a whole-universe book can do. A reader has to "
            "be able to tell that from a twin that accidentally copied the "
            "parent's picks, and this line is how."
            if (detail.get("universe_overlap_with_parent") or 0) >= 0.999
            else None),
    }


def plan(*, bars=None, asof: date | None = None, conn=None) -> dict:
    """Every book, what it carries, what it is owed, and the missing twins built.

    Nothing is written. The twins in `missing` are real `PaperBook` objects the
    apply step persists unchanged — computing them here and rebuilding them there
    would be two draws.
    """
    from backend.services import paper_books as PB

    asof = asof or date.today()
    if bars is None:
        try:
            bars = PB.load_bars()
        except Exception as exc:                                   # noqa: BLE001
            logger.warning("bars unavailable (%s)", exc)
            bars = None
    rows: list[dict] = []
    to_create: list[tuple] = []
    for book in PB.list_books(include_twins=False, conn=conn):
        have = carried_kinds(book, conn=conn)
        try:
            owed = owed_kinds(book, bars=bars, asof=asof)
        except Exception as exc:                                   # noqa: BLE001
            rows.append({"book_id": book.book_id,
                         "strategy_id": book.strategy.strategy_id,
                         "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        gap = [k for k in owed if k not in have]
        row = {"book_id": book.book_id,
               "strategy_id": book.strategy.strategy_id,
               "construction_rule": book.strategy.construction.rule,
               "cadence": book.cadence,
               "created_utc": book.created_utc,
               "carries": have, "owed_now": owed, "missing": gap,
               "expected_gap": book.strategy.strategy_id in EXPECTED_GAP}
        if gap:
            built = PB.make_twins(book.strategy, cadence=book.cadence,
                                  bars=bars, asof=asof)
            new = [t for t in built if (twin_kind(t) or "?") in gap]
            parent_syms = []
            try:
                parent_syms = PB.resolve_universe(book.strategy, bars, asof)                     if bars is not None else []
            except Exception:                                      # noqa: BLE001
                parent_syms = []
            row["parent_universe_size"] = len(parent_syms)
            row["missing_twins"] = [_twin_row(t, parent_syms) for t in new]
            to_create.append((book, new))
        rows.append(row)

    unmatched = [t["kind"] for r in rows for t in (r.get("missing_twins") or [])
                 if not t["matched"]]
    return {
        "receipt": "reseed_beta_twins", "roadmap_item": "chunk 12 T4",
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        # THE STAGE CONTRACT (`docs/STAGE_CONTRACT.md`). This scan reads bars and
        # a book registry and produces a UNIVERSE -- a matched list of tradable
        # names. It computes no signal, no weight and no PnL, so it is
        # `normalized`: the stage between the raw tape and anything ranked.
        "stage": "normalized",
        "stage_note": ("a twin's membership is a universe, not a signal. This "
                       "receipt may be read by a later stage and reads none."),
        "ran_at": _now(), "asof": str(asof),
        "bars_available": bars is not None,
        "armed": is_armed(), "arm_env": ARM_ENV, "applied": False,
        "defect": (
            "`LONG_ONLY_RULES` omitted `passthrough` when the first books were "
            "seeded on 2026-09-12, so lane B's two insider-cluster books -- the "
            "programme's only passthrough books -- were created with ONE twin "
            "where TRIAL-DRAFT-B names two. The tuple was fixed the same day; "
            "the books already existed, and `seed_first_books` correctly "
            "reports `created: false` and adds nothing."),
        "what_the_draw_depends_on": (
            "THE TWIN IS DRAWN AT TODAY'S BARS. A twin's book_id is the "
            "fingerprint of its contract and the contract carries its symbols, "
            "so this is not the twin the book would have had on 2026-09-12: it "
            "is matched on betas estimated over the 120 sessions ending "
            f"{asof}. Neither book has a NAV history, so nothing is "
            "retro-fitted -- but the control's membership is a fact about the "
            "control and it is recorded here rather than implied."),
        "books": rows,
        "n_books_scanned": len(rows),
        "n_books_with_a_gap": sum(1 for r in rows if r.get("missing")),
        "n_twins_to_create": sum(len(r.get("missing_twins") or []) for r in rows),
        "unmatched_kinds": unmatched,
        "degenerate_beta_matches": [
            {"parent": r["strategy_id"], "twin": t["book_id"],
             "n_symbols": t["n_symbols"]}
            for r in rows for t in (r.get("missing_twins") or [])
            if t.get("degenerate_beta_match")],
        "unmatched_warning": (
            "a beta-matched twin that could not be matched is a RANDOM draw and "
            "says so on its own row (`twin.UNMATCHED`). Applying one would add a "
            "control that is weaker than its name -- decide that deliberately, "
            "not as a side effect." if unmatched else None),
        "attended_command": attended_command(),
    }, to_create


def attended_command() -> str:
    return (f"{ARM_ENV}=1 python -m scripts.reseed_beta_twins --apply"
            f"   (PowerShell: $env:{ARM_ENV}='1'; "
            f"python -m scripts.reseed_beta_twins --apply)")


def apply_reseed(p: dict, to_create: list[tuple], *, conn=None) -> dict:
    """Persist the missing twins and extend their parents' `control_twin_ids`.

    REFUSES unless `AEGIS_RESEED_BETA_TWINS=1`. The parent row is rewritten with
    `dataclasses.replace`, so every other field is the one already on disk: a
    hand-built parent would be a new contract wearing an old id.
    """
    from backend.services import paper_books as PB

    if not is_armed():
        return {**p, "applied": False,
                "refused": (f"{ARM_ENV} is not 1. Adding a twin writes the "
                            f"PARENT's row as well (`control_twin_ids` lives "
                            f"there), which is a write into a seeded book's "
                            f"record. A session does not arm that for itself."),
                "attended_command": attended_command()}
    own = conn is None
    conn = conn or PB._conn()
    done: list[dict] = []
    try:
        for book, twins in to_create:
            ids = list(book.control_twin_ids)
            notes = [book.control_construction] if book.control_construction else []
            for t in twins:
                PB._persist(conn, t)
                ids.append(t.book_id)
                notes.append(f"{twin_kind(t)}: {t.control_construction}")
            parent = replace(book, control_twin_ids=tuple(ids),
                             control_construction=" | ".join(notes))
            PB._persist(conn, parent)
            done.append({"book_id": book.book_id,
                         "strategy_id": book.strategy.strategy_id,
                         "twins_added": [t.book_id for t in twins],
                         "control_twin_ids_now": ids})
    finally:
        if own:
            conn.close()
    return {**p, "applied": True, "created": done,
            "n_twins_created": sum(len(d["twins_added"]) for d in done)}


def print_plan(p: dict) -> None:
    print("=" * 74)
    print("BETA-MATCHED TWIN RE-SEED — the plan. Nothing has been written.")
    print("=" * 74)
    print(f"  asof {p['asof']}   bars {'loaded' if p['bars_available'] else 'ABSENT'}"
          f"   armed: {p['armed']}")
    print()
    for r in p["books"]:
        if r.get("error"):
            print(f"  {r['strategy_id']:40s} ERROR {r['error']}")
            continue
        mark = "GAP " if r["missing"] else "    "
        print(f"  {mark}{r['strategy_id']:40s} rule={r['construction_rule']:20s}")
        print(f"        carries {sorted(r['carries'])}  owed {r['owed_now']}")
        for t in r.get("missing_twins") or []:
            print(f"        + {t['kind']}  {t['book_id']}  {t['n_symbols']} names  "
                  f"{'MATCHED' if t['matched'] else 'UNMATCHED (a random draw)'}")
            print(f"          membership sha256 {t['symbols_sha256'][:16]}…  "
                  f"overlap with parent {t['universe_overlap_with_parent']}")
            if t.get("degenerate_beta_match"):
                print("          DEGENERATE: the twin's universe IS the parent's "
                      "universe -- matching a band's deciles to itself returns "
                      "the band")
            d = t.get("twin_detail") or {}
            if d.get("deciles_matched"):
                print(f"          deciles matched {d['deciles_matched']}"
                      + (f"  SHORT {d['deciles_short']}" if d.get("deciles_short") else ""))
            if t.get("overlap_note"):
                print("          overlap 1.0: the control works through the "
                      "SIGNAL alone (a passthrough parent's universe IS the band)")
    print(f"\n  {p['n_books_with_a_gap']} book(s) of {p['n_books_scanned']} are "
          f"short a twin; {p['n_twins_to_create']} twin(s) to create")
    if p.get("unmatched_warning"):
        print(f"\n  !! {p['unmatched_warning']}")
    print(f"\n  ATTENDED, and a session may not run it:\n      {p['attended_command']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help=f"write the twins; requires {ARM_ENV}=1")
    ap.add_argument("--json", action="store_true", help="print the receipt as JSON")
    ap.add_argument("--no-receipt", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    p, to_create = plan()
    if a.apply:
        p = apply_reseed(p, to_create)
    if not a.no_receipt:
        path = receipt_path()
        path.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
        p["receipt_path"] = str(path)
    if a.json:
        print(json.dumps(p, indent=1, default=str))
    else:
        print_plan(p)
        if p.get("refused"):
            print(f"\n  REFUSED: {p['refused']}")
        if p.get("applied"):
            print(f"\n  APPLIED: {p['n_twins_created']} twin(s) written")
    if not a.no_receipt:
        print(f"  receipt -> {p['receipt_path']}")
    # `--apply` without the flag is a REFUSAL, and a refusal is a finding: the
    # plan was still computed and written. A non-zero exit here would make a
    # scheduled caller look like a failure when it did exactly the right thing.
    return 0


__all__ = ["ARM_ENV", "DEGENERATE_COVERAGE", "EXPECTED_GAP", "apply_reseed", "attended_command",
           "carried_kinds", "is_armed", "main", "owed_kinds", "plan",
           "print_plan", "receipt_path", "twin_kind"]


if __name__ == "__main__":                                   # pragma: no cover
    sys.exit(main())
