"""Does the FIRST genuine IIF-1 record disarm the LIVE_FORWARD refusal?

    python -m scripts.verify_live_forward_disarm

READ-ONLY with respect to every real ledger. It reconstructs the volume's state
in a temporary directory and runs the real guard against it.

WHY THIS RUNS BEFORE NIGHT 1 AND NOT AFTER
==========================================
`ledger_resolver.resolve_due` refuses to grade LIVE_FORWARD while the
population is unestablished, and `evidence_population.live_forward_is_established`
decides that with

    established = shared < len(live)

Right now the volume holds 112 records, every one content-identical to a
CAMPAIGN_FORWARD record, so `112 < 112` is False and the refusal holds. The
predicate asks "is ANY record genuine?" where the decision it gates is "which
records may be graded" — so the first genuine write flips it for the whole
file, including the 112 copies, 25 of which are already overdue.

This is the house failure mode inverted. Every other guard this week fired when
it should not have; this one stops firing exactly when it starts to matter,
because it was written for a world containing nothing genuine.

AND THEN: IS IT ARMED ON MONDAY? NO — AND THE REASON IS ITS OWN FINDING
=======================================================================
The obvious reading is that IIF-1 Night 1 supplies that first genuine record.
It does not, and checking rather than assuming is the whole point of §2 below.

Night 1 runs **locally and attended** by ruling: the deployed image cannot run
a paying night because `verify_or_refuse()` needs an `Aegis module` sibling the
image does not have (`IIF1_PRE_NIGHT_1_CHECKLIST.md` §"Night 1 itself"). So
`investigator_night`'s `belief_state.append(all_records)` — no path, no
population — writes to whatever ledger Murat's machine calls default. Locally
the campaign and live paths COINCIDE, and `owner_of` breaks that tie in favour
of CAMPAIGN_FORWARD.

So the volume never sees Night 1. `112 < 112` stays False, the refusal holds,
and the disarm below does not fire on Monday.

What happens instead is the mirror of it: **the product's first genuine forward
records are born stamped `campaign_forward`**, appended to the 20,073-row
campaign ledger, and `stamp()` refuses to re-label a record afterwards ("a
record does not change population"). The mislabel is permanent by design, and
it lands on the one night the programme cannot repeat.

WHAT THIS SCRIPT DOES NOT DO
============================
It does not fix anything and it does not touch a real ledger. Both remedies are
attended: moving rows off the authoritative persisted ledger is irreversible
and outward-facing, and choosing where Night 1's records belong is a ruling,
not a patch.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from backend.services import evidence_population as EP
from backend.services import ledger_resolver as LR

#: The volume's contents, per the 2026-08-15 adjudication: the first 112 rows
#: of the campaign ledger, which reached it before the migration guard existed.
#: Four independent checks agree (12 specialists, 6 void, 1 model, last written
#: 2026-08-12). Reconstructed rather than fetched: this must run offline and
#: must not touch production.
N_VOLUME_ROWS = 112


def _campaign_rows(n: int) -> list[dict]:
    path = EP.ledger_path(EP.EvidencePopulation.CAMPAIGN_FORWARD)
    out: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
            if len(out) >= n:
                break
    return out


def _genuine_record(template: dict) -> dict:
    """One record that is NOT a copy — what Night 1 writes.

    Built off a real row so the shape is right, with the content-bearing fields
    changed so its hash cannot collide with a campaign record.
    """
    r = dict(template)
    r["prediction_id"] = "iif1-night1-synthetic-0001"
    r["specialist"] = "internet_investigator"
    r["ticker"] = "ZZZZ"
    r["made_at"] = "2026-08-17T12:00:00+00:00"
    r["resolves_after"] = "2026-11-15"
    r["outcome"] = None
    r["resolved_at"] = None
    r["thesis"] = "synthetic — this record exists only inside this check"
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--today", default=None,
                    help="ISO date to evaluate due-ness against")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    today = date.fromisoformat(a.today) if a.today else date.today()
    rows = _campaign_rows(N_VOLUME_ROWS)
    print(f"reconstructed {len(rows)} volume rows from the campaign ledger")
    stamped = sum(1 for r in rows if r.get("evidence_population"))
    print(f"  carrying an evidence_population stamp: {stamped}")
    print("  -> unstamped rows are attributed by FILE OWNERSHIP, so on the "
          "volume they read as live_forward and `assert_single_population` "
          "sees no foreign population. It is not a second barrier.")

    def _due(r: dict) -> bool:
        ra = r.get("resolves_after")
        if not ra or r.get("outcome") is not None or r.get("void_reason"):
            return False
        return date.fromisoformat(str(ra)[:10]) <= today

    n_due = sum(1 for r in rows if _due(r))
    print(f"  of those, DUE as of {today}: {n_due}")

    tmp = Path(tempfile.mkdtemp(prefix="live_forward_disarm_"))
    try:
        live = tmp / "predictions.jsonl"
        with live.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

        # On Railway the volume path IS the live ledger, so an unstamped row in
        # it is attributed to LIVE_FORWARD by ownership. That attribution is
        # reproduced here and NOTHING ELSE is patched — the predicate under
        # test, the resolver and the cross-write guard all run as shipped.
        # Locally the campaign and live paths coincide; in production they are
        # two files. Pointing LIVE_FORWARD at the temp copy reproduces the
        # production separation and leaves CAMPAIGN_FORWARD reading the real
        # ledger, which is what the predicate compares against.
        real_owner, real_path = EP.owner_of, EP.ledger_path

        def _owner(path):
            return (EP.EvidencePopulation.LIVE_FORWARD
                    if Path(path).resolve() == live.resolve()
                    else real_owner(path))

        def _path(pop):
            return (live if pop is EP.EvidencePopulation.LIVE_FORWARD
                    else real_path(pop))

        EP.owner_of, EP.ledger_path = _owner, _path

        before = EP.live_forward_is_established(path=live)
        print(f"\nBEFORE the first genuine write:")
        print(f"  n_records={before['n_records']}  "
              f"shared={before['n_shared_with_campaign']}  "
              f"established={before['established']}")

        with live.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_genuine_record(rows[0]),
                                ensure_ascii=False) + "\n")

        after = EP.live_forward_is_established(path=live)
        print(f"AFTER ONE genuine record:")
        print(f"  n_records={after['n_records']}  "
              f"shared={after['n_shared_with_campaign']}  "
              f"established={after['established']}")

        disarmed = (not before["established"]) and after["established"]
        print(f"\n  REFUSAL DISARMED BY ONE RECORD: {disarmed}")

        # ── and what the resolver would then do ────────────────────────────
        # `price_fetch` returns nothing, so nothing is actually graded here —
        # the question is whether the resolver REFUSES or PROCEEDS, and the
        # `due` count is how many records it would have carried into grading.
        import pandas as pd
        report = LR.resolve_due(live, population="live_forward",
                                price_fetch=lambda t, s, e: pd.DataFrame(),
                                today=today)
        status = report.get("status", "PROCEEDED")
        print(f"\nresolve_due(population='live_forward') -> {status}")
        print(f"  due={report.get('due')}  "
              f"newly_resolved={report.get('newly_resolved')}  "
              f"pending={report.get('pending')}")
        if status == "REFUSED":
            print("  the guard held.")
        else:
            print(f"  THE GUARD DID NOT HOLD. {report.get('due')} record(s) "
                  f"entered grading, and every one of them is campaign "
                  f"history. Nothing downstream filters by population: "
                  f"`resolve_all` rewrites the whole file.")

        print("\n§1 VERDICT: "
              + ("the predicate IS defective — one genuine record lifts the "
                 "refusal for the whole file."
                 if disarmed and status != "REFUSED" else
                 "NOT reproduced — re-read the predicate before acting."))
        broken = disarmed and status != "REFUSED"
    finally:
        EP.owner_of, EP.ledger_path = real_owner, real_path
        shutil.rmtree(tmp, ignore_errors=True)

    # ── §2 — but is it ARMED on Monday? Where does Night 1 actually write? ──
    print("\n" + "=" * 70)
    print("§2  WHERE NIGHT 1'S RECORDS LAND, on THIS machine")
    print("=" * 70)
    default = EP.ledger_path(EP.EvidencePopulation.LIVE_FORWARD)
    coincide = EP.paths_coincide()
    try:
        owner = EP.owner_of(default).value
    except EP.PopulationRequired:
        owner = "unattributable"
    print(f"  campaign path : {EP.ledger_path(EP.EvidencePopulation.CAMPAIGN_FORWARD)}")
    print(f"  live path     : {default}")
    print(f"  paths_coincide: {coincide}")
    print(f"  an unstamped record written here is attributed: {owner}")
    print("  `investigator_night` calls belief_state.append(records) with no "
          "path and no population, and Night 1 runs LOCALLY by ruling.")

    armed = (not coincide) and owner == "live_forward"
    if armed:
        print("\n  -> Night 1 WOULD reach the live population. The §1 disarm "
              "is ARMED: quarantine before the night.")
    else:
        print(f"\n  -> Night 1 does NOT reach the live population from here. "
              f"The §1 disarm is NOT armed on Monday.")
        print(f"     Instead the night's genuine records are stamped "
              f"{owner!r} and appended to the campaign ledger, and `stamp()` "
              f"refuses to re-label a record afterwards. That is permanent, "
              f"and it happens on a night that cannot be repeated.")

    print("\nBOTH FINDINGS STAND INDEPENDENTLY:")
    print(f"  predicate defective : {broken}   (fix before ANY genuine write "
          f"reaches the volume)")
    print(f"  armed on Monday     : {armed}   (this is the one that is "
          f"date-bound)")
    return 2 if (broken or not armed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
