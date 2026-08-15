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
from datetime import datetime, timedelta, timezone
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
                        universe: list[str] | None = None,
                        sandbox: bool = False, freeze: bool = True) -> dict:
    """Build the snapshot, write it, and report what could not be measured.

    `freeze=False` builds without writing. THIS IS WHAT `--readiness` NEEDS.

    WHY, found 2026-08-15 by reading the path before running it. A readiness
    check is supposed to spend nothing, and it does not spend money — but with
    `freeze=True` it spends the night's **one snapshot slot**. The decision
    timestamp is `now`, the snapshot is keyed by date, and `write_snapshot`
    refuses to overwrite (correctly — a re-assembled snapshot would substitute
    today's corrected calendar and adjusted prices for what the model saw).

    So a readiness check run six hours before a pre-open night freezes that
    night's point-in-time record six hours early, and the night then hits the
    45-minute decision-lag guard and REFUSES. That is the identical failure
    that voided the previous attempt, arriving through the one command whose
    documented purpose is to be safe. The guard belongs here, where the
    irreversible write is, not in the operator's memory of when to run it.
    """
    import time as _time
    ts = F.resolve_decision_ts(as_of)
    _t0 = _time.time()
    snap = F.assemble(ts, universe=universe)
    # HOW LONG THE INPUTS TOOK IS PART OF THE FRESHNESS BUDGET.
    #
    # `decision_ts` is stamped when assembly STARTS, and the night's staleness
    # guard measures `now - decision_ts` once, just before the first paid call.
    # So every minute spent assembling is a minute already spent from the
    # 45-minute allowance — and assembly walks the whole universe through
    # yfinance and EDGAR, which is minutes, not seconds. Nobody was measuring
    # it, which is how a budget gets consumed by the thing that checks it.
    snap["assembly_seconds"] = round(_time.time() - _t0, 1)
    snap["sandbox"] = bool(sandbox)
    path = (F.write_snapshot(snap, overwrite=overwrite, sandbox=sandbox)
            if freeze else None)

    sc = snap["status_counts"]
    print(f"decision_ts   {snap['decision_ts']}  ({snap['decision_ts_tz']})")
    print(f"universe      {snap['n_universe']} names")
    print(f"features      OK_DATA {sc.get('OK_DATA', 0)}  "
          f"OK_EMPTY {sc.get('OK_EMPTY', 0)}  "
          f"UNAVAILABLE {sc.get('UNAVAILABLE', 0)}")
    print(f"usable names  {snap['n_with_any_feature']}  "
          f"(fully unmeasured: {snap['n_fully_unavailable']})")
    print(f"snapshot      {path}" if path is not None else
          "snapshot      NOT WRITTEN — assembled in memory for the readiness "
          "report.\n              The night's point-in-time record is still "
          "unclaimed, which is\n              the only state from which a "
          "pre-open night can run.")

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


#: Microtask calls per (arm, cell). Five contracts: event, expectations,
#: forecast, critic, plus one tool-planning turn. Used ONLY for an upper bound.
CALLS_PER_CELL = 5


def readiness_report(snap: dict, sel: dict, *, as_of: str | None,
                     balance_usd: float, sandbox_snapshot: bool = False,
                     now: datetime | None = None) -> int:
    """Everything a human needs before authorising the first dollar. Spends $0.

    Deliberately ends with the literal command rather than a description of it.
    A readiness report whose last line is "then run the production night" makes
    the reader reconstruct the invocation, and the invocation is where the
    `sandbox=False` decision actually lives.
    """
    from backend.services import iif1_prereg as P
    from backend.services import investigator_night as N2

    print("\n" + "=" * 70)
    print("NIGHT-1 READINESS — nothing below spent money")
    print("=" * 70)

    # 1. the registered rule
    try:
        frozen = P.verify_or_refuse()
        print(f"\nfrozen prereg      MATCHES ({len(frozen)} fields verified)")
        print(f"  arms             {list(frozen['ARMS'])}")
        print(f"  triggers/night   {frozen['TRIGGERS_PER_NIGHT']}")
        print(f"  model requested  {frozen['REQUEST_MODEL']}")
        print(f"  ceilings         ${frozen['NIGHTLY_MAX_USD']:.2f} / "
              f"{frozen['NIGHTLY_MAX_CALLS']} calls")
        prereg_ok = True
    except Exception as exc:                                   # noqa: BLE001
        print(f"\nfrozen prereg      *** {type(exc).__name__}: {exc}")
        print("  a paying night will REFUSE until this resolves")
        frozen, prereg_ok = {}, False

    # 2. the inputs
    sc = snap["status_counts"]
    total = sum(sc.values()) or 1
    print(f"\ninputs             decision_ts {snap['decision_ts']}")
    print(f"  universe         {snap['n_universe']} names")
    print(f"  features         OK_DATA {sc.get('OK_DATA', 0)}  "
          f"OK_EMPTY {sc.get('OK_EMPTY', 0)}  "
          f"UNAVAILABLE {sc.get('UNAVAILABLE', 0)}  "
          f"({100.0 * sc.get('UNAVAILABLE', 0) / total:.1f}% unavailable)")
    if snap["unavailable"]:
        by_feat: dict[str, int] = {}
        for feats in snap["unavailable"].values():
            for k in feats:
                by_feat[k] = by_feat.get(k, 0) + 1
        print("  unavailable by   "
              + ", ".join(f"{k}={v}" for k, v in
                          sorted(by_feat.items(), key=lambda kv: -kv[1])))

    # 3. the pool
    k = int(frozen.get("TRIGGERS_PER_NIGHT", TR.TRIGGERS_PER_NIGHT))
    reachable = sel["n_selected"] >= k
    print(f"\ntrigger pool       {sel['n_eligible']} eligible, "
          f"{sel['n_excluded']} excluded")
    print(f"  selected         {sel['n_selected']}/{k}  "
          + ("REACHABLE" if reachable else "*** SHORT OF K — the frozen count "
                                           "is not reachable from this pool"))

    # 4. what it would cost, as a bound rather than a guess
    arms = list(frozen.get("ARMS", N2.ARMS))
    max_calls = sel["n_selected"] * len(arms) * CALLS_PER_CELL
    ceiling = float(frozen.get("NIGHTLY_MAX_USD", N2.NIGHTLY_MAX_USD))
    bound = max_calls * N2.WORST_CASE_CALL_USD
    print(f"\ncost              {sel['n_selected']} cells x {len(arms)} arms x "
          f"{CALLS_PER_CELL} microtasks = {max_calls} calls (upper bound)")
    print(f"  reserve/call     ${N2.WORST_CASE_CALL_USD:.4f} -> "
          f"${bound:.2f} worst case")
    print(f"  hard ceiling     ${ceiling:.2f}  "
          + ("(binds first — the night stops before the bound)"
             if bound > ceiling else "(the bound stays under it)"))
    print(f"  balance          ${balance_usd:.2f}   "
          f"planning average ${balance_usd / N2.GRADED_NIGHTS_TO_FIRST_LOOK:.3f}"
          f"/night over {N2.GRADED_NIGHTS_TO_FIRST_LOOK} nights")
    print("  NOTE             this is a BOUND, not an estimate. The number "
          "that decides funding is measured from served responses after the "
          "night, never predicted before it.")

    # 5. where the evidence lands
    print(f"\nreceipts           {N2.RECEIPTS_DIR}")
    print(f"  sandbox receipts {N2.SANDBOX_RECEIPTS_DIR}")
    print(f"  feature snapshot "
          f"{F.snapshot_path(F.resolve_decision_ts(as_of), sandbox=sandbox_snapshot)}"
          + ("   [SANDBOX]" if sandbox_snapshot else ""))

    # 6. THE SESSION WINDOW — added 2026-08-15, after the guard was found to
    # have invented a Sunday opening bell. This report is the human gate before
    # the first dollar and it said nothing about whether tonight is a session,
    # so a reader could be told READY on a Saturday. The night itself would
    # have refused (that is what the guard is for), but a readiness report that
    # can say READY when the exchange is shut is a report that trains its
    # reader to overrule the guard.
    window_ok, window_note = True, ""
    try:
        from backend.services import market_sessions as MS
        _now = now or datetime.now(timezone.utc)
        _nxt = MS.next_session_open(_now)
        print(f"\nsession window     next XNYS open {_nxt.isoformat(timespec='minutes')}"
              f"  ({(_nxt - _now).total_seconds() / 3600.0:.1f}h away)")
        print(f"  today            {_now.date().isoformat()} "
              + ("IS a session" if MS.is_session(_now.date())
                 else "is NOT a session"))
        for _conc, _label in ((1, "serial     "), (N2.MAX_ARM_CONCURRENCY,
                                                   "concurrent ")):
            _m = N2.projected_night_minutes(k=k, n_arms=len(arms),
                                            arm_concurrency=_conc)
            _m90 = N2.projected_night_minutes(
                k=k, n_arms=len(arms), arm_concurrency=_conc,
                call_seconds=N2.MEASURED_CALL_SECONDS_P90)
            print(f"  {_label}      {_m:5.0f} min projected, latest start "
                  f"{(_nxt - timedelta(minutes=_m)).strftime('%H:%M')}Z "
                  f"(at p90 latency {(_nxt - timedelta(minutes=_m90)).strftime('%H:%M')}Z)")
        try:
            _rep = N2.assert_night_fits_before_open(
                k=k, n_arms=len(arms), now=_now,
                arm_concurrency=N2.MAX_ARM_CONCURRENCY)
            print(f"  headroom         {_rep['minutes_of_headroom']:.0f} min "
                  f"at the declared {_rep['concurrency_efficiency_declared']}x "
                  f"efficiency (DECLARED, never yet measured)")
        except N2.NightWouldSpanTheOpen as exc:
            window_ok = False
            window_note = str(exc).split(".")[0]
            print(f"  *** {window_note}")
    except Exception as exc:                                     # noqa: BLE001
        window_ok = False
        window_note = f"session calendar unavailable: {exc}"
        print(f"\nsession window     *** {window_note}")

    blockers = []
    if not window_ok:
        blockers.append(window_note)
    if sandbox_snapshot:
        blockers.append("this is a SANDBOX snapshot (rehearsal or hand-picked "
                        "universe) — a paying night must be frozen against a "
                        "production snapshot of the full universe")
    if not prereg_ok:
        blockers.append("frozen pre-registration unreadable")
    if not reachable:
        blockers.append(f"trigger pool cannot fill {k}")
    print("\n" + "-" * 70)
    if blockers:
        print("NOT READY: " + "; ".join(blockers))
        return 1

    print("READY. Nothing above spent money. The command that WOULD:\n")
    stamp = f' --as-of "{as_of}"' if as_of else ""
    # NO `--reuse-snapshot`, and the reason is this report.
    #
    # It used to say `--reuse-snapshot`, because readiness froze a snapshot as
    # a side effect. It no longer does — freezing here would consume the
    # night's one point-in-time slot hours early and guarantee the staleness
    # refusal. So there is nothing to reuse, and the instruction had to change
    # with the behaviour. Leaving it would have handed a FileNotFoundError to
    # whoever typed the last line of a report that had just said READY.
    print(f"    python -m backend.services.iif1_run{stamp}")
    print("\nThat invocation ASSEMBLES A FRESH SNAPSHOT and then runs with "
          "sandbox=False. It verifies the frozen pre-registration on the real "
          "path, refuses every override, and writes the forward evidence "
          "ledger. It is the first dollar.")
    print("\nTIMING MATTERS AND THE ASSEMBLY IS PART OF IT. `decision_ts` is "
          "stamped when\nassembly begins and the staleness guard allows "
          f"{N.MAX_DECISION_LAG_MINUTES} minutes; this report's own assembly "
          "took\n"
          f"{_assembly_note(snap)}. Start the night so that assembly plus the "
          "night itself\nfits the window — do not assemble in advance and run "
          "later.")
    return 0


def _assembly_note(snap: dict) -> str:
    s = snap.get("assembly_seconds")
    if not s:
        return "an unrecorded amount of time"
    return (f"{s / 60.0:.0f} minutes, leaving roughly "
            f"{max(0, N.MAX_DECISION_LAG_MINUTES - s / 60.0):.0f} of the "
            f"{N.MAX_DECISION_LAG_MINUTES}-minute allowance")


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
    ap.add_argument("--readiness", action="store_true",
                    help="print the pre-spend readiness report and the exact "
                         "command that would spend money; spends nothing")
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

    # A rehearsal, or a hand-picked universe, is not a production night, and its
    # snapshot must not claim a production date. A six-name test snapshot in the
    # production namespace freezes that night against a pool that cannot fill
    # the frozen trigger count -- and the immutability rule then refuses to
    # correct it.
    snap_sandbox = bool(a.rehearse or universe)
    if a.reuse_snapshot:
        snap = F.load_snapshot(ts, sandbox=snap_sandbox)
        print(f"reusing frozen {'sandbox ' if snap_sandbox else ''}snapshot for "
              f"{ts.date()} (assembled {snap.get('assembled_at')})")
    else:
        # A readiness check must not claim the night's snapshot slot — see
        # `assemble_and_freeze`. `--assemble-only` is the flag that exists to
        # freeze deliberately, and it still does.
        snap = assemble_and_freeze(a.as_of, overwrite=a.overwrite_snapshot,
                                   universe=universe, sandbox=snap_sandbox,
                                   freeze=not a.readiness)

    sel = preview_triggers(snap)

    if a.readiness:
        return readiness_report(snap, sel, as_of=a.as_of,
                                balance_usd=a.balance_usd,
                                sandbox_snapshot=snap_sandbox)

    if a.assemble_only:
        print("\n--assemble-only: inputs frozen, nothing was reasoned about "
              "and nothing was spent.")
        return 0

    if a.rehearse:
        print("\nREHEARSAL — sandbox, stub model, $0.00. This exercises "
              "parsing, minting, pairing and the receipt writer; it proves "
              "nothing about the vendor.")
        # `transport=`, not `llm_call=`. Injecting the client replaced the
        # budget gate, the telemetry write and the chain cursor along with the
        # vendor, so the rehearsal reported `n_chains: 0` and could not have
        # revealed the chain-yield divergence that voided Night 1. Swapping only
        # the wire leaves every layer that broke inside the simulation.
        res = N.run_night(snap["features"], transport=stub_llm,
                          tool_runner=stub_tools, dry_run=False, sandbox=True,
                          balance_usd=a.balance_usd,
                          night=str(ts.date()))
    else:
        print("\nPRODUCTION NIGHT — the effective invocation is verified "
              "against the frozen pre-registration before anything is spent.")
        res = N.run_night(snap["features"], dry_run=False, sandbox=False,
                          balance_usd=a.balance_usd,
                          decision_ts=snap["decision_ts"],
                          night=str(ts.date()))

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
