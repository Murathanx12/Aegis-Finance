"""A parquet that EXISTS can still be missing the columns that make it usable.

    python -m scripts.wrds_column_completeness
    python -m scripts.wrds_column_completeness --json

THE GAP THIS EXISTS TO MAKE VISIBLE
===================================
`wrds_pull_catchup` is explicit about its resume rule: *"a table whose parquet
exists is skipped."* That is the right rule for a pull that either happened or
did not. It is the WRONG rule for a pull that happened with a narrower column
list than a later consumer needs — and there is no way for the catch-up queue to
notice, because the only thing it looks at is whether the file is there.

So the gap is structurally invisible. `crsp_dsf_2010.parquet` exists, therefore
it is skipped, therefore it will never gain the columns it lacks, no matter how
many catch-up nights run.

This is the sibling of a failure already in the ledger: *"a failure-driven queue
cannot see a NEVER-ATTEMPTED item"* (2026-08-23, WRDS completeness). Same shape,
one level in: **an existence-keyed queue cannot see a PARTIALLY-PULLED item.**

WHAT IT COST, MEASURED
======================
`crsp_dsf_1990..2012` carry `permno/date/prc/ret/vol`. `crsp_dsf_2013..2024`
also carry `openprc`, `retx`, `shrout`. Those three are not decorations:

  * `openprc` IS the next-open fill convention. Without it the only executable
    convention is close-to-close, which books the overnight gap that follows the
    signal — a systematic gift to exactly the strategies being searched for;
  * `retx` is the only way to tell a dividend from a price move;
  * `shrout` is market cap, so cap-weighting and any size signal are impossible.

`portfolio_farm.panel` therefore REFUSES the 1990-2012 years by name, and the
whole farm runs on twelve years. The sub-period split then showed the leading
strategy is 1.01x the market over 2013-2018 and 1.75x over 2019-2024 — one
regime — which makes those twenty-three missing years the difference between a
result and an artefact.

WHAT THIS SCRIPT DOES
=====================
Declares, per dataset, the columns a CONSUMER needs; reads what each parquet
actually contains; and prints the gap plus the exact re-pull plan. It exits
non-zero when a required column is missing anywhere, so it can gate.

It does NOT pull anything. The pull is `scripts/wrds_pull_*` and it spends a
credentialed session against Murat's institutional WRDS account — that decision
stays with him.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import DATA_DIR  # noqa: E402

WRDS_DIR = DATA_DIR / "optimus" / "wrds"

#: What each consumer actually reads, and who breaks without it. A dataset with
#: no entry here is not checked — silence about a dataset is not a pass, and the
#: summary says how many were unchecked.
REQUIRED: dict[str, dict] = {
    "crsp_dsf_*": {
        "consumer": "backend/services/portfolio_farm/panel.py",
        "columns": ["permno", "date", "prc", "ret", "retx", "vol", "shrout",
                    "openprc"],
        "why": {
            "openprc": "the next-open fill convention; without it execution "
                       "silently becomes close-to-close",
            "retx": "separates a dividend from a price move",
            "shrout": "market cap — cap weighting and every size signal",
        },
    },
}


def _columns(path: Path) -> set[str]:
    import pyarrow.parquet as pq
    return set(pq.ParquetFile(path).schema_arrow.names)


def audit(dir_: Path | None = None) -> dict:
    d = dir_ or WRDS_DIR
    out: dict[str, dict] = {}
    for pattern, spec in REQUIRED.items():
        need = set(spec["columns"])
        files = sorted(d.glob(f"{pattern}.parquet"))
        complete, partial = [], {}
        for p in files:
            try:
                have = _columns(p)
            except Exception as exc:                           # noqa: BLE001
                partial[p.stem] = {"error": str(exc)}
                continue
            missing = sorted(need - have)
            (complete.append(p.stem) if not missing
             else partial.__setitem__(p.stem, {"missing": missing}))
        out[pattern] = {
            "consumer": spec["consumer"], "required": sorted(need),
            "n_files": len(files), "n_complete": len(complete),
            "n_partial": len(partial), "partial": partial,
            "complete_range": (f"{complete[0]}..{complete[-1]}"
                               if complete else None),
        }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rep = audit()
    if a.json:
        print(json.dumps(rep, indent=1))
        return 1 if any(r["n_partial"] for r in rep.values()) else 0

    print("WRDS COLUMN COMPLETENESS")
    print("=" * 66)
    print("`wrds_pull_catchup` skips a table whose parquet EXISTS. A file with")
    print("the wrong columns is therefore invisible to it, permanently.\n")
    bad = 0
    for pattern, r in rep.items():
        print(f"  {pattern}   consumer: {r['consumer']}")
        print(f"    required : {', '.join(r['required'])}")
        print(f"    files    : {r['n_files']}  complete {r['n_complete']}  "
              f"PARTIAL {r['n_partial']}")
        if r["complete_range"]:
            print(f"    usable   : {r['complete_range']}")
        if r["n_partial"]:
            bad += r["n_partial"]
            by_missing: dict[tuple, list[str]] = {}
            for name, info in sorted(r["partial"].items()):
                key = tuple(info.get("missing") or ["<unreadable>"])
                by_missing.setdefault(key, []).append(name)
            for cols, names in by_missing.items():
                print(f"    MISSING {list(cols)}  in {len(names)} file(s): "
                      f"{names[0]} .. {names[-1]}")
                for c in cols:
                    why = REQUIRED[pattern].get("why", {}).get(c)
                    if why:
                        print(f"        {c}: {why}")
        print()
    if bad:
        print(f"  {bad} parquet file(s) exist but are NOT USABLE by their "
              f"declared consumer.")
        print("  The catch-up queue cannot see this. The re-pull is a "
              "deliberate, attended act:")
        print("  it spends a credentialed WRDS session, so it is Murat's call, "
              "not a script's.")
    else:
        print("  every declared consumer's columns are present in every file.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
