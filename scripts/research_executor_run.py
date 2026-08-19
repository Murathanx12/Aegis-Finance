"""AEGIS-RESEARCH-EXECUTOR-1 — first real run over the declared queue.

    python -m scripts.research_executor_run            # classify only
    python -m scripts.research_executor_run --execute  # run runnable jobs

Every one of the 13 declared jobs gets an explicit status: RUNNABLE (an
adapter exists and its gates clear), BLOCKED (reason in words — signature,
conventions, absent data), or NO_ADAPTER (the unit of work that makes the
job real is building one). Blocked is a finding, not a failure: the first
factory receipt converts "tests_run: 0" into a legible map of exactly what
stands between each question and its answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import research_daemon as RD          # noqa: E402
from backend.services import research_executor as RE        # noqa: E402
from scripts.research_daemon_first_queue import FIRST_QUEUE  # noqa: E402

#: Why each currently-unrunnable job is unrunnable, in words. A reason here
#: is DELIBERATE; an id in neither table is ACTIONABLE (build the adapter).
BLOCKED_REASONS = {
    "HJ-EFFECTIVE-SPREAD-1": (
        "verdict deferred to trade-condition conventions (external review "
        "Q3: tr_scond/odd-lot/TRF-latency); v1 dataset exists as immutable "
        "sensitivity"),
    "CONVEXITY-PRESERVATION-1": (
        "trim-vs-hold verdict needs its signed pre-registration (canon §6); "
        "the INSTRUMENT_AUDIT below runs meanwhile"),
    "EVENT-RESOLUTION-CURVE-1": (
        "needs the PIT event store with announcement timestamps — specced "
        "in the day-factory handoff, not yet materialized"),
    "PURE-NEWS-RESIDUAL-1": (
        "needs the expected-news model trained strictly pre-article — PIT "
        "text store absent"),
    "IMPLIED-REVISION-1": (
        "SHELF by design: PIT analyst-report text entitlement unverified "
        "(probe, not catalogue)"),
    "INFORMATION-PROCESSING-GAP-1": "needs the PIT event store (as above)",
    "OPTIONS-EQUITY-DISLOCATION-1": (
        "needs the OptionMetrics PIT store + OPTION-PIT-AUDIT-1 look-ahead "
        "controls first"),
    "REACTION-GAP-1": "needs the PIT event store (as above)",
    "INFORMATION-HALF-LIFE-1": (
        "needs disclosure-delay event data (PTR/13D/Form 4) with filing "
        "timestamps materialized"),
    "NEWS-X-FLOW-1": "no credible PIT retail-flow proxy on hand — SHELF",
    "SEQUENCE-OF-EVIDENCE-1": "needs the PIT event store (as above)",
    "CROSS-ENTITY-LAG-1": (
        "needs dated relation-graph snapshots (no static present-day graph "
        "applied backward)"),
    "MODEL-DISAGREEMENT-1": (
        "needs at least two additional PIT modality stores before "
        "disagreement exists to measure"),
}


def build() -> tuple[RD.ResearchDaemon, RE.Executor]:
    d = RD.ResearchDaemon()              # reserved windows DERIVED
    for job in FIRST_QUEUE:
        d.submit(job)
    ex = RE.Executor(d)
    for job in FIRST_QUEUE:
        hid = job.hypothesis_id
        if hid == "CONVEXITY-PRESERVATION-1":
            # the audit reads the job's own declared period/universe
            ex.register(RE.JobAdapter(
                hypothesis_id=hid, kind=RE.KIND_INSTRUMENT_AUDIT,
                reads_universe=job.universe, reads_start=job.start,
                reads_end=job.end, run=RE.convexity_power_audit))
        elif hid in BLOCKED_REASONS:
            ex.register(RE.JobAdapter(
                hypothesis_id=hid, kind=RE.KIND_RESULT,
                reads_universe=job.universe, reads_start=job.start,
                reads_end=job.end, run=lambda: None,
                blocked_reason=BLOCKED_REASONS[hid]))
    return d, ex


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="research_executor_run")
    ap.add_argument("--execute", action="store_true",
                    help="run runnable jobs (audits included); default is "
                         "classify-only")
    ap.add_argument("--max-jobs", type=int, default=2)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    d, ex = build()
    print("=" * 78)
    print("AEGIS-RESEARCH-EXECUTOR-1 — queue classification")
    print("=" * 78)
    for hid, c in ex.classify_all().items():
        status = c["status"]
        line = f"  {status:<10} {hid}"
        if status != RE.RUNNABLE:
            line += f"  — {c['reason'][:90]}"
        print(line)

    if not a.execute:
        print("\n--execute not given: classified only, nothing ran.")
        return 0

    receipt = ex.run_ready(max_jobs=a.max_jobs)
    p = ex.write_receipt(receipt)
    print(f"\nexecuted={len(receipt['executed'])} "
          f"audited={len(receipt['audited'])} "
          f"failed={len(receipt['failed'])} "
          f"blocked={len(receipt['blocked'])} "
          f"no_adapter={len(receipt['no_adapter'])}")
    for aud in receipt["audited"]:
        print(f"  audit {aud['hypothesis_id']}: "
              f"{json.dumps(aud['audit'])[:160]}")
    print(f"receipt: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
