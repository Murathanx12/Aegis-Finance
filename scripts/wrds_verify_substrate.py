"""Does every parquet in the substrate actually contain its whole table?

THE CHECK THAT WAS MISSING. A pull reports pulled/failed counts, and a clean
failure count is not the same as correct output: on 2026-08-20 a run reported
"0 failures" while writing 23 files that each held an arbitrary 4–80% of their
table (`SELECT * ... LIMIT cap` with no ORDER BY). Nothing in the pipeline
compared what landed against what exists.

This does, per file:

    rows_in_file   from the parquet footer (no full read)
    rows_on_server SELECT count(*) with the SAME universe filter the pull used
    verdict        COMPLETE / TRUNCATED / SHORT / EXTRA / UNVERIFIED

The universe filter matters: tables keyed by permno were pulled with
`WHERE permno = ANY(...)`, so their file legitimately holds fewer rows than
the table. Comparing against an unfiltered count would flag every one of them
as truncated — correct arithmetic against the wrong world, which is the
failure this file exists to catch, not commit.

UNVERIFIED is a real verdict, not a pass. A count that timed out or a table
that has since vanished leaves the file's status unknown, and unknown must
never be rendered as fine.

    python -m scripts.wrds_verify_substrate
    python -m scripts.wrds_verify_substrate --limit 50
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.wrds_pull_everything import BULK, MANIFEST, MAX_ROWS  # noqa: E402
from scripts.wrds_training_pull import OUT, _all_permnos, _conn    # noqa: E402

REPORT = OUT / "substrate_verification.json"
COUNT_TIMEOUT_MS = 120_000

#: WHAT A LATER COUNT CAN AND CANNOT PROVE.
#:
#: These tables are LIVE. A count taken hours after the pull is not the count
#: the pull saw, so `rows_in_file < rows_on_server` has two causes that a
#: count alone cannot separate: the server grew, or we lost rows. Observed on
#: the first run — `comp.aco_amda` 70,344 in file vs 70,345 on server, one
#: row, and four more between 0.01% and 0.03%. Those are Compustat adding
#: rows, not a truncated pull.
#:
#: So the verdicts are stated at the strength the evidence supports:
#:   TRUNCATED  n_file is EXACTLY the cap and the server has more. This is
#:              provable: the cap is the only reason a pull stops at that
#:              number, and it is the defect this file was written for.
#:   SHORT_MINOR  below the drift tolerance — consistent with the table having
#:              grown. NOT a clean bill of health, just not evidence of loss.
#:   SHORT_MAJOR  too large to be drift. Investigate.
#: Calling a minor short "COMPLETE" would be the same overclaim as calling a
#: truncated file complete, one order of magnitude smaller.
DRIFT_TOLERANCE = 0.005          # 0.5%


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100000)
    a = ap.parse_args()

    import pyarrow.parquet as pq

    # THE FILTER DECISION COMES FROM THE PLAN, NOT THE MANIFEST.
    #
    # The first version read `universe_filtered` out of the manifest's
    # `pulled` rows. The manifest is BOOKKEEPING that a running pull appends
    # to, so a verifier that snapshots it at startup races the pull: three
    # tables pulled minutes earlier were not yet in the snapshot, read as
    # unfiltered, and were reported as having lost half their rows —
    #     crsp.erdport5   6,112,111 in file vs 12,324,256 unfiltered = 49.6%
    # A re-count WITH the permno filter returned 6,112,111 exactly. All three
    # were false alarms raised by the tool written to stop false assurance,
    # which is the same error in the other direction.
    #
    # The PLAN is static and is what the pull itself keys on
    # (`id_col in permno/lpermno/permco` -> WHERE permno = ANY(...)), so
    # deriving the filter from it cannot race anything.
    from scripts.wrds_pull_everything import PLAN_CACHE
    try:
        plan = json.loads(PLAN_CACHE.read_text(encoding="utf-8"))
        pmap = {p["name"]: p for p in plan.get("plan", [])}
    except Exception as exc:                                    # noqa: BLE001
        print(f"  (plan cache unreadable: {exc}) — cannot derive filters")
        pmap = {}
    man = (json.loads(MANIFEST.read_text(encoding="utf-8"))
           if MANIFEST.exists() else {})
    meta = {p.get("name"): p for p in (man.get("pulled") or [])}

    #: The exact predicate `wrds_pull_catchup` / `wrds_pull_everything` apply.
    PERMNO_COLS = ("permno", "lpermno", "permco")

    files = sorted(BULK.glob("*.parquet"))[: a.limit]
    print(f"verifying {len(files)} parquet(s) against the server\n")

    permnos = None
    conn = _conn()
    cur = conn.cursor()
    rows, counts = [], {}
    for f in files:
        schema, _, table = f.stem.partition("__")
        name = f"{schema}.{table}"
        try:
            n_file = pq.ParquetFile(f).metadata.num_rows
        except Exception as exc:                                # noqa: BLE001
            rows.append({"name": name, "file": f.name, "verdict": "CORRUPT",
                         "error": str(exc)[:120]})
            print(f"  CORRUPT    {name}")
            continue

        pl = pmap.get(name) or meta.get(name) or {}
        id_col = pl.get("id_col")
        filtered = id_col in PERMNO_COLS
        where, params = "", None
        if filtered:
            if permnos is None:
                permnos = sorted(_all_permnos())
            where = f' WHERE "{id_col}" = ANY(%(p)s)'
            params = {"p": permnos}
        try:
            cur.execute(f"SET statement_timeout = {COUNT_TIMEOUT_MS}")
            cur.execute(f"SELECT count(*) FROM {schema}.{table}{where}",
                        params)
            n_srv = int(cur.fetchone()[0])
        except Exception as exc:                                # noqa: BLE001
            conn.rollback()
            rows.append({"name": name, "file": f.name, "verdict": "UNVERIFIED",
                         "rows_in_file": n_file, "error": str(exc)[:100]})
            print(f"  UNVERIFIED {name:<40s} file={n_file:>10,}  "
                  f"({str(exc)[:50]})")
            continue

        short_by = n_srv - n_file
        if n_file == n_srv:
            verdict = "COMPLETE"
        elif n_file == MAX_ROWS and n_srv > MAX_ROWS:
            verdict = "TRUNCATED"          # provable — see DRIFT_TOLERANCE
        elif n_file < n_srv:
            verdict = ("SHORT_MINOR"
                       if n_srv and short_by / n_srv <= DRIFT_TOLERANCE
                       else "SHORT_MAJOR")
        else:
            # More rows locally than the server reports: the table shrank, or
            # this file is from a different vintage. Either way it is not the
            # table it is named after.
            verdict = "EXTRA"
        rows.append({"name": name, "file": f.name, "verdict": verdict,
                     "rows_in_file": n_file, "rows_on_server": n_srv,
                     "short_by": short_by, "universe_filtered": filtered,
                     "kept_pct": (round(100.0 * n_file / n_srv, 2)
                                  if n_srv else None)})
        counts[verdict] = counts.get(verdict, 0) + 1
        if verdict != "COMPLETE":
            print(f"  {verdict:<10s} {name:<40s} file={n_file:>10,} "
                  f"server={n_srv:>12,}  kept={rows[-1]['kept_pct']}%")
    conn.close()

    for v in ("CORRUPT", "UNVERIFIED"):
        counts[v] = sum(1 for r in rows if r["verdict"] == v)
    print("\n=== VERDICTS ===")
    for k in sorted(counts):
        if counts[k]:
            print(f"  {counts[k]:>5,}  {k}")
    clean = [r for r in rows if r["verdict"] in ("COMPLETE", "SHORT_MINOR")]
    broken = [r for r in rows
              if r["verdict"] in ("TRUNCATED", "SHORT_MAJOR", "EXTRA",
                                  "CORRUPT")]
    unknown = [r for r in rows if r["verdict"] == "UNVERIFIED"]
    print(f"\n{len(clean):,} of {len(rows):,} files are complete or within "
          f"{DRIFT_TOLERANCE:.1%} drift")
    print(f"{len(broken):,} are BROKEN (truncated / short / extra / corrupt)")
    print(f"{len(unknown):,} are UNVERIFIED — status unknown, NOT a pass")

    REPORT.write_text(json.dumps({
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_files": len(rows), "by_verdict": counts,
        "drift_tolerance": DRIFT_TOLERANCE,
        "note": ("rows_on_server is counted with the SAME universe filter the "
                 "pull used. These tables are LIVE, so a count taken after "
                 "the pull cannot separate 'the server grew' from 'we lost "
                 "rows' — only an exactly-at-cap file is PROVABLY truncated. "
                 "SHORT_MINOR is consistent with drift and is not a clean "
                 "bill of health. UNVERIFIED is not a pass."),
        "files": rows,
    }, indent=2), encoding="utf-8")
    print(f"report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
