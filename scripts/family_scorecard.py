"""CLI for `backend.services.family_scorecard` (CH-55): one row per strategy family.

    python -m scripts.family_scorecard --data-root <optimus dir> --out <dir>
    python -m scripts.family_scorecard --data-root <optimus dir> --out <dir> --rebuild-dna
    python -m scripts.family_scorecard ... --false-fire-receipt <table2_*.json>

Reads the newest `paper_accounts/roi_<run>.json` + `book_dna_<run>.json` pair under the data
root (prints its run id, date and sizes first), and writes into `--out` -- never into the data
root -- `family_scorecard_<run>.json` + `.md` and the regenerated `results_voice_<run>.json` +
`.md`. `--rebuild-dna` re-runs book_dna with the current code into `--out` first (for receipts
written before the market-exposure block existed); it reads the prices and the books through
`backend.config`, so the data root must be the one this checkout is configured for (set
`AEGIS_DATA_DIR` to the parent of the data root to read another one, read-only).

Exit codes: 0 = written and complete. 2 = REFUSED, nothing written, with a named reason
(EMPTY_INPUT, UNREADABLE_INPUT, STALE_INPUT, STALE_MARKS, UNDATED_INPUT, NO_EXPOSURE_BLOCK,
OUT_INSIDE_INPUT, REBUILD_FAILED). A future-dated stamp or mark is UNDATED_INPUT, never fresh. 3 = written but FAILED: a live book with neither beta and residual nor
an explicit CANNOT DETERMINE with a reason, or a label without its false-fire rate.
$0, no LLM, no network, no order.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402
from backend.services import family_scorecard as FS  # noqa: E402
from backend.services import results_voice as RV  # noqa: E402

RC_OK, RC_REFUSED, RC_FAILED = 0, 2, 3


def count_files(folder: Path) -> int:
    """Files directly in a folder this script READS (builder rule: print before and after)."""
    return sum(1 for x in folder.iterdir() if x.is_file()) if folder.is_dir() else -1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="family_scorecard")
    ap.add_argument("--data-root", default=str(_config.OPTIMUS_LEDGER_DIR),
                    help="the optimus data folder (holds paper_accounts/); read-only")
    ap.add_argument("--out", required=True, help="output folder (never inside the data root)")
    ap.add_argument("--run-id", default=None, help="YYYY-MM-DDTHHMMSSZ; default: the newest shared run id")
    ap.add_argument("--rebuild-dna", action="store_true",
                    help="re-run book_dna on the ROI receipt into --out with the current code")
    ap.add_argument("--false-fire-receipt", default=None,
                    help="a scripts.paper_tables table2_*.json to read the labels' false-fire rates from "
                         "(default: config.LABEL_FALSE_FIRE_MEASURED)")
    ap.add_argument("--now", default=None, help="UTC time to date the input against (default: the clock)")
    ap.add_argument("--json", action="store_true", help="print one JSON summary line")
    a = ap.parse_args(argv)
    try:                       # a cp1252 console must not crash the run AFTER the receipts are written
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

    def refused(why: str) -> int:
        print(json.dumps({"status": "refused", "why": why}) if a.json else f"REFUSED family_scorecard: {why}")
        return RC_REFUSED

    root, out = Path(a.data_root), Path(a.out)
    pa = root / "paper_accounts"
    if out.resolve() == root.resolve() or out.resolve().is_relative_to(root.resolve()):
        return refused(f"OUT_INSIDE_INPUT: --out {out} is inside the data root {root}")
    if a.rebuild_dna and root.resolve() != Path(_config.OPTIMUS_LEDGER_DIR).resolve():
        return refused(f"REBUILD_FAILED: --rebuild-dna reads prices and books through backend.config, which points "
                       f"at {_config.OPTIMUS_LEDGER_DIR}, not at --data-root {root}; set AEGIS_DATA_DIR to "
                       f"{root.parent} for this run")
    try:
        now = datetime.fromisoformat(a.now.replace("Z", "+00:00")) if a.now else datetime.now(timezone.utc)
        now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    except ValueError:
        return refused(f"EMPTY_INPUT: --now {a.now!r} is not a time")
    n_before = count_files(pa)
    try:
        ff = RV.false_fire_from_table2(Path(a.false_fire_receipt)) if a.false_fire_receipt else None
        rid = a.run_id or (max(RV.run_ids(pa, "roi") or {""}) if a.rebuild_dna else RV.newest_shared_run_id(pa))
        if not a.json:
            sizes = {p.name: p.stat().st_size for p in (pa / f"roi_{rid}.json", pa / f"book_dna_{rid}.json")
                     if p.is_file()}
            print(f"input: run {rid} in {pa} ({n_before} files); " + ", ".join(f"{k} {v:,} bytes" for k, v in sizes.items()))
        res = FS.run(pa, out, run_id=rid, now=now, rebuild_dna=a.rebuild_dna, false_fire=ff)
    except RV.ResultsVoiceRefused as exc:
        msg = str(exc)
        return refused(msg if msg.split(":")[0].replace("_", "").isupper() else f"EMPTY_INPUT: {msg}")
    n_after = count_files(pa)
    sc = res["scorecard"]
    if a.json:
        print(json.dumps({"status": sc["status"], "run_id": res["run_id"], "json": res["json"], "md": res["md"],
                          "top_line": sc["top_line"], "coverage_line": sc.get("coverage_line"),
                          "failures": sc["failures"],
                          "live_folder_files": [n_before, n_after]}))
    else:
        age = sc["input_age"]
        print(f"input age: {age['age_days']} days (generated {age['generated_utc']}, limit {age['stale_days']:g})")
        print(sc["top_line"] + ".")
        if sc.get("coverage_line"):                      # CH-65: who is in none of the counts
            print(sc["coverage_line"] + ".")
        print(sc["second_line"] + ".")
        lead, worst = FS.ends(sc)
        print("Leaders are chosen after the fact, each over its own short window: an observation, not a "
              "skill claim.")
        for i, f in enumerate(lead, 1):
            print(f"LEADING {i}: {FS.family_line(f)}")
        for i, f in enumerate(worst, 1):
            print(f"WORST {i}: {FS.family_line(f)}")
        au = sc["exposure_audit"]
        print(f"exposure audit: {au['n_live_books']} live books, {au['n_beta_and_residual']} with beta and residual, "
              f"{au['n_cannot_determine_with_reason']} CANNOT DETERMINE with a reason, {au['n_missing']} with neither")
        print(f"live folder files before/after: {n_before}/{n_after}")
        print(f"wrote {res['json']}, {res['md']}, {res['results_voice_json']}, {res['results_voice_md']}")
        for x in sc["failures"]:
            print(f"FAILED: {x}")
    if n_after != n_before:
        # reported, not a refusal: this script writes only into --out, and a scheduled pass may
        # legitimately add a receipt to the live folder while it runs
        print(f"WARNING family_scorecard: {pa} held {n_before} files before and {n_after} after; this script "
              f"writes only into --out -- check which writer added them")
    return RC_FAILED if sc["status"] != "OK" else RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
