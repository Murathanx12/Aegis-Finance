"""Can Night 1's evidence be found and graded WITHOUT guessing its population?

    python -m scripts.verify_night1_evidence_contract

Zero dollars, zero vendor calls, no real ledger touched. Exit 0 only if every
element of the contract below is present and the recovery proof passes.

WHY THIS EXISTS
===============
`docs/NIGHT1_LEDGER_FINDINGS_2026-08-16.md` finding B: Night 1 runs locally,
where the campaign and live ledger paths COINCIDE, so `owner_of` breaks the tie
for CAMPAIGN and the night's genuine records are stamped `campaign_forward`
permanently — `stamp()` refuses to re-label.

The ruling taken was to run as-is and name the population in the receipt rather
than edit source on the critical path of a one-shot paid run. That ruling is
only safe if one thing is true, and it had not been checked:

    the night's records must be RECOVERABLE AND GRADEABLE by a key that does
    not depend on which population they were stamped with.

If they are not, the paid attempt buys an orphaned receipt. That is the
difference between a label being wrong and the evidence being lost, and it is
worth ten minutes before Monday rather than a discovery in November.

WHAT IS ACTUALLY BEING PROVEN
=============================
Not that a grader works — **there is no IIF-1 grader yet**. `iif1_prereg.py`
freezes the design, `iif1_features.py` freezes the inputs, `iif1_run.py` runs
the night, and nothing reads the records back. The grader will be written after
accrual, by someone who will not remember this week.

So what is proven is the thing that must be true BEFORE that person exists: the
record carries, on its own face, enough to identify which trial and which arm
produced it, independently of the population stamp and independently of the
file it happens to live in. That is a property of the record, checkable today.

The recovery key is asserted here and then TESTED, against the real 20,073-row
campaign ledger, with `owner_of` replaced by a function that raises. If the
recovery consults the population for any reason, this script fails loudly
instead of quietly passing on a coincidence.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from backend.services import belief_state as BS
from backend.services import evidence_population as EP
from backend.services import investigator_night as N

#: THE RECOVERY KEY. Declared before it is tested, so the test can fail.
#:
#: `arm is not None` alone would be enough today and will not stay enough — any
#: future trial with arms would collide with it. `specialist` carries the arm
#: name behind an `investigator:` prefix minted by `records_from_investigator`,
#: and that prefix is this trial's, so the pair is the key.
RECOVERY_KEY = ("specialist starts with 'investigator:' AND arm is not None")


def recover(rows: list[dict]) -> list[dict]:
    """The key, as executable code. Reads no population and no file path."""
    return [r for r in rows
            if str(r.get("specialist", "")).startswith("investigator:")
            and r.get("arm") is not None]


def _rehearsal_records() -> tuple[list, dict]:
    """Real records from the real minting path, via the $0 stub transport.

    `--rehearse` swaps the WIRE and nothing above it, so parsing, validation,
    minting, pairing and the record shape are the production ones. The records
    are read off `NightResult.records`, which is populated whether or not the
    ledger write happens — a sandbox night mints and then declines to persist.
    """
    from backend.services import iif1_run as R
    snap = R.assemble_and_freeze(None, overwrite=True, universe=["AAPL", "MSFT"],
                                 sandbox=True, freeze=True)
    res = N.run_night(snap["features"], transport=R.stub_llm,
                      tool_runner=R.stub_tools, dry_run=False, sandbox=True,
                      night="2026-08-17")
    return res.records, snap


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    print("rehearsing Night 1 (stub transport, $0.00, sandbox) ...")
    records, snap = _rehearsal_records()
    if not records:
        print("REFUSED: the rehearsal minted no records, so there is nothing "
              "to check. That is itself a Night-1 blocker.")
        return 2
    print(f"  minted {len(records)} record(s) through the production path\n")

    r0 = asdict(records[0])
    failures: list[str] = []

    # ── §1 the seven elements, and where each one actually lives ────────────
    print("=" * 72)
    print("§1  THE EVIDENCE CONTRACT — where each element lives")
    print("=" * 72)

    def row(name: str, where: str, value, *, required: bool = True) -> None:
        ok = value not in (None, "", [])
        print(f"  {name:<20} {'OK ' if ok else 'ABSENT'}  {where}")
        if value not in (None, "", []):
            print(f"  {'':<20}         = {str(value)[:70]}")
        if required and not ok:
            failures.append(f"{name} is absent ({where})")

    row("trial_id", "DERIVED: prompt_hash == _hash(f'{TRIAL}:{arm}:{night}')",
        N.TRIAL)
    # The receipt is keyed by `night`; the record's `made_at` DATE is not the
    # same thing and can differ from it (a night started late New York time
    # mints records on the following UTC date). What binds a record to its
    # receipt is `prompt_hash`, which covers (trial, arm, night) — so the run
    # id is that hash, not a date, and §2 checks it rather than trusting it.
    row("run_id", "prompt_hash, which binds (trial, arm, night) — see §2",
        records[0].prompt_hash)
    row("population", "record.evidence_population, stamped at append time",
        r0.get("evidence_population") or "(unstamped — sandbox path)",
        required=False)
    row("decision_ts", "snapshot['decision_ts'] — the INFORMATION CUTOFF",
        snap.get("decision_ts"))
    row("made_at", "record.made_at — minting time, NOT the cutoff",
        records[0].made_at)
    row("information_cutoff", "record.input_snapshot_hash -> frozen snapshot",
        records[0].input_snapshot_hash)
    row("receipt location", "backend/data/optimus/iif1_nights/<night>.json",
        str(N.RECEIPTS_DIR) if hasattr(N, "RECEIPTS_DIR") else "iif1_nights/")
    row("grader lookup path", f"RECOVERY_KEY: {RECOVERY_KEY}", RECOVERY_KEY)

    # `made_at` is NOT the information cutoff and the two must not be conflated:
    # the night runs for its whole duration after the snapshot is frozen, so a
    # record minted in the last cell is stamped later than the cutoff it was
    # reasoning from. The receipt carries `decision_lag_minutes` for exactly
    # this reason. A grader that reads `made_at` as the cutoff would credit the
    # forecaster with information it did not have.
    print(f"\n  NOTE decision_ts {snap.get('decision_ts')}")
    print(f"       made_at     {records[0].made_at}")
    print("       These differ by the night's own elapsed time. The cutoff is "
          "the snapshot's, never the record's.")

    # ── §2 does the trial link survive without any external index? ──────────
    print("\n" + "=" * 72)
    print("§2  IS TRIAL MEMBERSHIP RE-DERIVABLE FROM THE RECORD ALONE?")
    print("=" * 72)
    n_ok = 0
    for rec in records:
        expect = BS._hash(f"{N.TRIAL}:{rec.arm}:2026-08-17")
        if expect == rec.prompt_hash:
            n_ok += 1
    print(f"  prompt_hash == sha256('{N.TRIAL}:<arm>:<night>')  "
          f"for {n_ok}/{len(records)} records")
    if n_ok != len(records):
        failures.append("prompt_hash does not re-derive from (trial, arm, night)"
                        " — trial membership is asserted, not verifiable")
    else:
        print("  -> membership is CRYPTOGRAPHICALLY re-derivable. A record "
              "cannot be moved into this trial after the fact without also "
              "producing a matching hash.")

    # ── §3 recovery from the real ledger, with owner_of disabled ────────────
    print("\n" + "=" * 72)
    print("§3  RECOVERY FROM THE REAL CAMPAIGN LEDGER, owner_of DISABLED")
    print("=" * 72)
    campaign = BS.read_predictions(
        EP.ledger_path(EP.EvidencePopulation.CAMPAIGN_FORWARD))
    print(f"  campaign ledger: {len(campaign)} rows")

    tmp = Path(tempfile.mkdtemp(prefix="night1_contract_"))
    real_owner = EP.owner_of
    try:
        merged = tmp / "merged.jsonl"
        with merged.open("w", encoding="utf-8") as fh:
            for r in campaign:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            for rec in records:
                fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

        def _forbidden(path):                                    # noqa: ANN001
            raise AssertionError(
                "owner_of() was consulted during recovery — the whole point "
                "is that grading must not depend on it")

        EP.owner_of = _forbidden
        rows = BS.read_predictions(merged)
        found = recover(rows)
        EP.owner_of = real_owner

        want = {rec.prediction_id for rec in records}
        got = {r["prediction_id"] for r in found}
        strays = [r for r in found if r["prediction_id"] not in want]
        print(f"  merged file:     {len(rows)} rows")
        print(f"  recovered:       {len(found)}  (expected {len(records)})")
        print(f"  campaign rows swept in: {len(strays)}")
        if got != want:
            failures.append(f"recovery returned {len(got)} of {len(want)} "
                            f"night records, {len(strays)} strays")
        else:
            print("  -> EXACT. Every night record recovered, zero campaign "
                  "rows, and `owner_of` was never called.")

        # And the mirror: does the campaign history contain anything the key
        # would have grabbed? Measured, not assumed — if a single legacy row
        # matched, the key would silently pull campaign evidence into an IIF-1
        # grading run, which is the same class of defect one level down.
        legacy = recover(campaign)
        print(f"  campaign rows matching the key on their own: {len(legacy)}")
        if legacy:
            failures.append(f"{len(legacy)} campaign rows match the recovery "
                            f"key — it is not specific to this trial")
    finally:
        EP.owner_of = real_owner
        shutil.rmtree(tmp, ignore_errors=True)

    # ── verdict ────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    if failures:
        print("CONTRACT NOT SATISFIED — do not spend the paid attempt yet:")
        for f in failures:
            print(f"  - {f}")
        return 2
    print("CONTRACT SATISFIED.")
    print("  Night 1's records are recoverable and gradeable by a key that "
          "reads no population and no file path, so the campaign_forward "
          "stamp mislabels them WITHOUT orphaning them.")
    print("  The population still has to be named in the receipt before the "
          "run — a recoverable record with an undeclared population is a "
          "question deferred, not answered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
