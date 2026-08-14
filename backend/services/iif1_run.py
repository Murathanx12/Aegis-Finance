"""INTERNET-INVESTIGATOR-FWD-1 — the entrypoint. This is how a night is run.

    # 1. rehearse: no vendor, no money, produces the receipt Night 1 would
    python -m backend.services.iif1_run --rehearse

    # 2. freeze the inputs (real data, still no LLM)
    python -m backend.services.iif1_run --assemble-only

    # 3. the real thing
    python -m backend.services.iif1_run

WHY THIS FILE EXISTS
====================
`run_night()` was written, tested and reviewed, and had no caller. A library
function with twenty-four tests and no invocation path is not a runnable pilot,
and the distance between the two is exactly this file plus `iif1_features`.

THE ORDER IS NOT ARBITRARY
==========================
Features are assembled and **frozen to disk before a single vendor call**. The
night then reads the frozen snapshot. Assembling inside the run would make the
inputs a side effect of the run, so a crash halfway through would leave a night
whose inputs no longer exist and whose partial spend bought nothing auditable.

Three modes, and only one of them can spend:

  `--rehearse`      sandbox + a deterministic stub model. Zero dollars. Proves
                    the plumbing end to end and prints the receipt shape.
  `--assemble-only` real data, frozen snapshot, no model at all. This is the
                    step that tells you whether the trigger list is sane before
                    paying to reason about it.
  (default)         production. Verifies the effective invocation against the
                    frozen pre-registration, refuses every override, and writes
                    the forward evidence ledger.

WHERE IT RUNS
=============
Locally, attended, for the pilot. `verify_or_refuse()` needs the `Aegis module`
sibling holding the frozen pre-registration, and the deployed image does not
carry it — deliberately, because a context that cannot read the registered rule
must not accrue against it. Packaging the frozen artifact with a content hash is
the automation step, and it is earned after the pilot is stable, not designed in
before the first night.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from backend.services import iif1_features as F
from backend.services import investigator_night as N
from backend.services import investigator_triggers as TR

logger = logging.getLogger(__name__)


def stub_llm(*, system: str, user: str, model: str = "stub",
             temperature: float = 0.0, max_tokens: int = 1600) -> Any:
    """A deterministic model for rehearsals. Never touches a network.

    It answers each microtask with the minimum valid shape, so a rehearsal
    exercises parsing, validation, minting, pairing and the receipt writer —
    everything except the vendor.
    """
    from backend.services.investigator_agent import FORECAST_CELLS

    class _Reply:
        def __init__(self, text: str):
            self.text = text
            self.model_version = "stub-rehearsal"
            self.tokens_in = 0
            self.tokens_out = 0
            self.cached_tokens = 0
            self.latency_ms = 0.0
            self.retries = 0

    if "Extract what changed" in system:
        body = {"what_changed": "rehearsal", "when": "n/a",
                "who_is_affected": [], "novelty": "low",
                "expectedness": "fully_expected", "unknowns": []}
    elif "prior_market_belief" in system:
        body = {"prior_market_belief": "n/a",
                "what_moved_in_expectations": "n/a", "already_priced": "n/a"}
    elif "MAGNITUDE" in system:
        body = {"forecasts": [
            {"observable": o, "horizon_days": h, "threshold": t,
             "prior": 0.20, "posterior": 0.20,
             "rationale": "rehearsal: belief unchanged"}
            for o, h, t in FORECAST_CELLS]}
    elif "strongest_objection" in system:
        body = {"strongest_objection": "n/a", "contradicting_evidence": "n/a",
                "falsifying_check": "n/a", "confidence_in_chain": "low"}
    else:
        body = {"calls": [], "done": True}
    return _Reply(json.dumps(body))


def stub_tools(name: str, args: dict, budget: Any = None):
    from backend.services import investigator_tools as IT
    return IT.ToolResult(name, IT.STATUS_EMPTY)


def assemble_and_freeze(as_of: str | None, *, overwrite: bool = False,
                        universe: list[str] | None = None) -> dict:
    """Build the snapshot, write it, and report what could not be measured."""
    ts = F.resolve_decision_ts(as_of)
    snap = F.assemble(ts, universe=universe)
    path = F.write_snapshot(snap, overwrite=overwrite)

    sc = snap["status_counts"]
    print(f"decision_ts   {snap['decision_ts']}  ({snap['decision_ts_tz']})")
    print(f"universe      {snap['n_universe']} names")
    print(f"features      OK_DATA {sc.get('OK_DATA', 0)}  "
          f"OK_EMPTY {sc.get('OK_EMPTY', 0)}  "
          f"UNAVAILABLE {sc.get('UNAVAILABLE', 0)}")
    print(f"usable names  {snap['n_with_any_feature']}  "
          f"(fully unmeasured: {snap['n_fully_unavailable']})")
    print(f"snapshot      {path}")

    # An unmeasured security is not a calm one, so the count is printed rather
    # than left for someone to notice in a JSON file.
    if snap["unavailable"]:
        worst: dict[str, int] = {}
        for feats in snap["unavailable"].values():
            for k in feats:
                worst[k] = worst.get(k, 0) + 1
        print("unavailable by feature: "
              + ", ".join(f"{k}={v}" for k, v in sorted(worst.items(),
                                                        key=lambda kv: -kv[1])))
    return snap


def preview_triggers(snap: dict, k: int = TR.TRIGGERS_PER_NIGHT) -> dict:
    sel = TR.select_triggers(snap["features"], k=k)
    print(f"\ntriggers      {sel['n_selected']}/{k} selected from "
          f"{sel['n_eligible']} eligible / {sel['n_universe']} scored"
          + ("  [SHORT OF K — disclosed, never padded]"
             if sel["short_of_k"] else ""))
    for row in sel["selected"][:10]:
        print(f"  {row['ticker']:<6s} score {row['score']:.3f}"
              + (f"   {row['reason']}" if row.get("reason") else ""))
    if sel["n_selected"] > 10:
        print(f"  ... {sel['n_selected'] - 10} more")
    return sel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="iif1_run", description=f"Run one {N.TRIAL} night.")
    ap.add_argument("--as-of", default=None,
                    help="decision timestamp, New York time (default: now)")
    ap.add_argument("--rehearse", action="store_true",
                    help="sandbox + stub model; zero dollars")
    ap.add_argument("--assemble-only", action="store_true",
                    help="freeze the feature snapshot and stop")
    ap.add_argument("--reuse-snapshot", action="store_true",
                    help="read tonight's frozen snapshot instead of building it")
    ap.add_argument("--overwrite-snapshot", action="store_true",
                    help="rebuild a snapshot that already exists (only if that "
                         "night never ran)")
    ap.add_argument("--universe", default=None,
                    help="comma-separated tickers, for rehearsals")
    ap.add_argument("--balance-usd", type=float, default=N.DEFAULT_BALANCE_USD,
                    help="current vendor balance, for the funding projection")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    # The Windows console defaults to cp1252, which cannot encode the box
    # characters this report uses — and the crash lands AFTER the night has run,
    # so a real night would have spent the money and then died printing the
    # receipt it had already written. Found in the first rehearsal.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ts = F.resolve_decision_ts(a.as_of)
    universe = ([u.strip().upper() for u in a.universe.split(",") if u.strip()]
                if a.universe else None)

    if a.reuse_snapshot:
        snap = F.load_snapshot(ts)
        print(f"reusing frozen snapshot for {ts.date()} "
              f"(assembled {snap.get('assembled_at')})")
    else:
        snap = assemble_and_freeze(a.as_of, overwrite=a.overwrite_snapshot,
                                   universe=universe)

    preview_triggers(snap)

    if a.assemble_only:
        print("\n--assemble-only: inputs frozen, nothing was reasoned about "
              "and nothing was spent.")
        return 0

    if a.rehearse:
        print("\nREHEARSAL — sandbox, stub model, $0.00. This exercises "
              "parsing, minting, pairing and the receipt writer; it proves "
              "nothing about the vendor.")
        res = N.run_night(snap["features"], llm_call=stub_llm,
                          tool_runner=stub_tools, dry_run=False, sandbox=True,
                          balance_usd=a.balance_usd,
                          night=str(ts.date()))
    else:
        print("\nPRODUCTION NIGHT — the effective invocation is verified "
              "against the frozen pre-registration before anything is spent.")
        res = N.run_night(snap["features"], dry_run=False, sandbox=False,
                          balance_usd=a.balance_usd, night=str(ts.date()))

    print(f"\nstatus        {res.status}"
          + (f"  ({res.void_reason})" if res.void_reason else ""))
    print(f"cells         {len(res.tickers)} tickers x {len(res.per_arm)} arms")
    if res.cell_pairing:
        cp = res.cell_pairing
        print(f"pairing       {cp['n_cells_paired']} paired / "
              f"{cp['n_cells_union']} produced  "
              f"({cp['n_cells_dropped_unpaired']} dropped unpaired)")
    print(f"records       {res.records_written} written"
          + ("  [sandbox: nothing reached the evidence ledger]"
             if res.sandbox else ""))
    print(f"served models {res.served_models or ['(none)']}")

    b = res.budget or {}
    print("\n── funding ──")
    print(f"  measured_cost_night_1     {b.get('measured_cost_night_1')} "
          f"({b.get('measured_cost_status')})")
    print(f"  projected_40_night_cost   {b.get('projected_40_night_cost')}")
    print(f"  current_balance           {b.get('current_balance')}")
    print(f"  funding_gap_or_surplus    {b.get('funding_gap_or_surplus')}")
    print(f"  fundable_nights_at_rate   {b.get('fundable_nights_at_this_rate')}"
          f" / {b.get('nights_required')} required")
    print(f"  funding_average_per_night {b.get('funding_average_per_night')} "
          f"(the planning number)")
    print(f"  safety_ceiling_per_night  {b.get('safety_ceiling_per_night')} "
          f"(a stop, not a plan)")

    return 0 if res.status in ("ok", "budget_stopped") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
