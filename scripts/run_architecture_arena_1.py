"""LLM-ARCHITECTURE-ARENA-1 — run the arms, measure P1, write the report.

    python scripts/run_architecture_arena_1.py --pilot 8      # measure first
    python scripts/run_architecture_arena_1.py --items 120    # the run
    python scripts/run_architecture_arena_1.py --a5 60        # the model tier
    python scripts/run_architecture_arena_1.py --report-only

THE DESIGN IS PAIRED AND THE PAIRING IS THE POINT
-------------------------------------------------
Every arm sees the IDENTICAL item set — the same securities with the same
observation timestamp, taken from the frozen LLM-SWARM-1 universe so that the
control is running against the exact inputs that produced the 0.2996 it is
being compared to. Items are drawn once with a fixed seed and reused by every
arm; an arm that got a different draw would be a different experiment.

WHAT IS WRITTEN WHERE
---------------------
* Forward prediction records -> `predictions.jsonl` (the forward-only ledger),
  keyed `arena_<ARM>`, resolving from 2026-08-16. This is P3.
* Historical records, if a historical pass is ever run, -> a SEPARATE file.
  `predictions.jsonl` has never been backfilled and this trial does not start.
* Cell rows -> `backend/data/arena/arena_1_cells.jsonl` (checkpoint, resumable).
* Report -> `docs/LLM_ARCHITECTURE_ARENA_1.md`, artifact ->
  `docs/llm_architecture_arena_1.json`.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:                                       # pragma: no cover
    print("python-dotenv missing — relying on the ambient environment")

from backend import config as cfg                          # noqa: E402
from backend.services import architecture_arena as aa      # noqa: E402
from backend.services import belief_state as bs            # noqa: E402
from backend.services import llm_swarm as sw               # noqa: E402
from backend.services import research_budget               # noqa: E402

RUN_DIR = ROOT / "backend" / "data" / "arena"
CHECKPOINT = RUN_DIR / "arena_1_cells.jsonl"
RUN_META = RUN_DIR / "arena_1_run_meta.json"
ITEMS_FILE = RUN_DIR / "arena_1_items.json"
UNIVERSE = ROOT / "backend" / "data" / "swarm" / "swarm_1_universe.json"
REGISTRY = Path(r"C:\Users\mrthn\Aegis module\TRIALS\registry.jsonl")
REPORT = ROOT / "docs" / "LLM_ARCHITECTURE_ARENA_1.md"
ARTIFACT = ROOT / "docs" / "llm_architecture_arena_1.json"

#: The prereg's declared allocation for THIS agent, tighter than the campaign
#: ceiling the governor enforces. Both are checked; the governor is authority.
ALLOC_USD = 12.0
ALLOC_CALLS = 20000

SEED = 20260812

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("arena")


# ── the item set ────────────────────────────────────────────────────────────

def load_items(n: int) -> tuple[dict[str, dict], str]:
    """N securities drawn once, with a fixed seed, from the FROZEN SWARM-1
    universe.

    Reused rather than rebuilt on purpose. A0 is the control and the corpse, and
    the only way its 0.2996 is a meaningful reference point is if the arms are
    run against the same snapshots that produced it. Rebuilding the universe
    tonight would introduce a second difference (a different draw of securities)
    into a comparison designed to have exactly one.

    The draw is SHUFFLE-ONCE-THEN-TAKE-THE-FIRST-N rather than `sample(k=n)`,
    so the pilot's items are a strict SUBSET of the full run's. Every pilot call
    is therefore a call already paid for that the main run reuses, and the two
    are not two different experiments sharing a checkpoint file.
    """
    u = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    snaps: dict[str, dict] = u["snapshots"]
    keys = sorted(snaps)
    random.Random(SEED).shuffle(keys)
    picked = sorted(keys[:min(n, len(keys))])
    return {k: snaps[k] for k in picked}, u["as_of"]


def build_peers(all_snaps: dict[str, dict], items: dict[str, dict],
                *, per_item: int = 5) -> dict[str, list[dict]]:
    """Same-sector peers for A4's `peers` tool, from the frozen panel only.

    Deterministic (sorted, then seeded shuffle) so a rerun serves the identical
    peer set: a tool whose answer changes between runs would put an
    uncontrolled difference inside the arm that is supposed to be measuring
    retrieval.
    """
    by_sector: dict[str, list[str]] = defaultdict(list)
    for t, s in sorted(all_snaps.items()):
        by_sector[str(s.get("sector") or s.get("vendor_sector") or "Unknown")
                  ].append(t)
    out: dict[str, list[dict]] = {}
    for t, s in items.items():
        sec = str(s.get("sector") or s.get("vendor_sector") or "Unknown")
        pool = [x for x in by_sector.get(sec, []) if x != t]
        random.Random(SEED + hash(t) % 10_000).shuffle(pool)
        out[t] = [{
            "ticker": p, "sector": sec,
            "trailing_return_pct": all_snaps[p].get("trailing_return_pct"),
            "realised_vol_annualised_pct":
                all_snaps[p].get("realised_vol_annualised_pct"),
            "beta_vs_benchmark": all_snaps[p].get("beta_vs_benchmark"),
        } for p in pool[:per_item]]
    return out


def personas_for(snap: dict) -> list[str]:
    """Every SWARM-1 specialist eligible for this security, SWARM-1's own rule.

    A0 must be the architecture it is standing in for, not a cheaper sample of
    it: the 0.2996 came from many personas colliding on one security, and an A0
    that ran one persona per name would not contain the phenomenon under test.
    """
    sec = str(snap.get("sector", "Unknown"))
    vend = str(snap.get("vendor_sector", "") or "")
    return [name for name, spec in sw.SPECIALISTS.items()
            if spec.sectors is None or sec in spec.sectors
            or vend in spec.sectors]


# ── cells ───────────────────────────────────────────────────────────────────

def plan(items: dict[str, dict], arms: list[str],
         a0_persona_cap: int | None) -> list[tuple[str, str, str]]:
    """(arm, item, persona) cells, shuffled with a fixed seed.

    Shuffled so a run stopped early by the governor is a RANDOM subsample of the
    grid rather than the alphabetical front of it, and so no arm is
    systematically the one that ran before the budget tightened.
    """
    cells: list[tuple[str, str, str]] = []
    for t, s in items.items():
        for arm in arms:
            if arm == "A0":
                ps = personas_for(s)
                if a0_persona_cap:
                    ps = ps[:a0_persona_cap]
                cells.extend(("A0", t, p) for p in ps)
            else:
                cells.append((arm, t, ""))
    random.Random(SEED).shuffle(cells)
    return cells


def load_checkpoint() -> tuple[list[dict], set[str]]:
    if not CHECKPOINT.exists():
        return [], set()
    rows, done = [], set()
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            log.warning("checkpoint: an unreadable line was skipped — its cell "
                        "will be re-run, which costs a call and loses nothing")
            continue
        rows.append(r)
        done.add(f"{r['arm']}|{r['item']}|{r.get('persona', '')}|"
                 f"{r.get('leg', '')}")
    return rows, done


# ── the run ─────────────────────────────────────────────────────────────────

def run(args: argparse.Namespace) -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    since = str(started.date())

    st = research_budget.check(aa.CAMPAIGN, since=None)
    print(f"budget at start: {json.dumps(st.as_dict())}", flush=True)
    if not st.ok:
        print(f"REFUSING TO START — {st.reason}")
        return 2
    spend0 = float(st.cost_usd or 0.0)
    calls0 = int(st.n_calls or 0)

    u = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    n_items = args.pilot or args.items
    items, as_of = load_items(n_items)
    peers = build_peers(u["snapshots"], items)
    registry = aa.load_registry(REGISTRY)
    print(f"{len(items)} items as of {as_of}; registry rows {len(registry)}",
          flush=True)
    ITEMS_FILE.write_text(json.dumps(
        {"as_of": as_of, "seed": SEED, "items": sorted(items),
         "n_registry_rows": len(registry)}, indent=1), encoding="utf-8")

    arms = args.arms.split(",") if args.arms else list(aa.ARMS)
    cells = plan(items, arms, args.a0_persona_cap)
    rows, done = load_checkpoint()
    todo = [c for c in cells
            if f"{c[0]}|{c[1]}|{c[2]}|" not in done]
    print(f"planned {len(cells)} cells, {len(done)} already done, "
          f"{len(todo)} to run, {args.workers} workers", flush=True)
    if not todo:
        print("nothing to do")
        return 0

    made_at = started.isoformat(timespec="seconds")
    lock = threading.Lock()
    ck = CHECKPOINT.open("a", encoding="utf-8")
    counts: Counter = Counter()
    pending: list[Any] = []
    halted: str | None = None
    t0 = time.perf_counter()

    def caller(messages, **kw):
        return aa.call_model(messages, since=None, **kw)

    def work(cell: tuple[str, str, str], leg_model: str = aa.FLASH,
             leg: str = "") -> Any:
        arm, tkr, persona = cell
        snap = items[tkr]
        kwargs: dict[str, Any] = {"caller": caller, "model": leg_model}
        if arm == "A0":
            kwargs["persona"] = persona
        if arm == "A4":
            kwargs["ctx"] = aa.ToolContext(snapshot=snap,
                                           peers=peers.get(tkr, []),
                                           registry=registry)
        res = aa.RUNNERS[arm](snap, **kwargs)
        return res, snap, leg

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, c): c for c in todo}
        try:
            for i, fut in enumerate(as_completed(futs), 1):
                cell = futs[fut]
                try:
                    res, snap, leg = fut.result()
                except aa.ResearchBudgetExhausted as exc:
                    halted = str(exc)
                    break
                except Exception as exc:                  # noqa: BLE001
                    counts[f"{cell[0]}:failed"] += 1
                    log.warning("cell %s crashed: %s: %s", cell,
                                type(exc).__name__, exc)
                    continue
                recs = (aa.mint(res, snapshot=snap, made_at=made_at)
                        if res.status == "ok" else [])
                with lock:
                    counts[f"{res.arm}:{res.status}"] += 1
                    row = res.as_row()
                    row["leg"] = leg
                    row["prediction_ids"] = [r.prediction_id for r in recs]
                    rows.append(row)
                    pending.extend(recs)
                    ck.write(json.dumps(row, default=str) + "\n")
                    if i % 25 == 0:
                        ck.flush()
                    if len(pending) >= 150:
                        bs.append(pending)
                        pending = []
                    if i % 50 == 0:
                        b = research_budget.check(aa.CAMPAIGN, since=None)
                        spent = float(b.cost_usd or 0.0) - spend0
                        made = int(b.n_calls or 0) - calls0
                        rate = i / max(time.perf_counter() - t0, 1e-9) * 60
                        print(f"[{i}/{len(todo)}] {dict(counts)} "
                              f"this-run ${spent:.3f} / {made} calls "
                              f"{rate:.0f} cells/min", flush=True)
                        if spent >= ALLOC_USD or made >= ALLOC_CALLS:
                            # The agent's OWN allocation, tighter than the
                            # campaign ceiling. Stopping here is not the
                            # governor refusing; it is this run keeping the
                            # promise it made before it started.
                            halted = (f"agent allocation reached: ${spent:.2f} "
                                      f"of ${ALLOC_USD} / {made} of "
                                      f"{ALLOC_CALLS} calls")
                            break
        finally:
            if halted:
                for f in futs:
                    f.cancel()
            with lock:
                if pending:
                    bs.append(pending)
                    pending = []
                ck.flush()
                ck.close()

    wall = time.perf_counter() - t0
    b = research_budget.check(aa.CAMPAIGN, since=None)
    RUN_META.write_text(json.dumps({
        "started_utc": made_at, "wall_clock_min": round(wall / 60, 1),
        "workers": args.workers, "halted": halted, "as_of": as_of,
        "n_items": len(items), "arms": arms, "seed": SEED,
        "spend_this_run_usd": round(float(b.cost_usd or 0.0) - spend0, 6),
        "calls_this_run": int(b.n_calls or 0) - calls0,
        "budget_at_end": b.as_dict(),
    }, indent=1), encoding="utf-8")
    if halted:
        print(f"\nHALTED: {halted}")
    print(f"\ndone in {wall/60:.1f} min: {dict(counts)}")
    print(f"spend this run: ${float(b.cost_usd or 0.0) - spend0:.4f} over "
          f"{int(b.n_calls or 0) - calls0} calls")
    return 0


# ── A5 · the model tier ─────────────────────────────────────────────────────

def run_a5(args: argparse.Namespace) -> int:
    """The best arm re-run paired on flash vs pro, on a subset of the items.

    `served_model` is the whole reason this arm can be believed. The last time a
    model comparison was run here it was `deepseek-chat` against
    `deepseek-reasoner`, both of which the vendor resolves to
    `deepseek-v4-flash` — a null manufactured by a config bug. Both legs are
    verified against the response body before anything is reported.
    """
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    rows, done = load_checkpoint()
    if not rows:
        print("no main run in the checkpoint — run the arms first")
        return 2
    best = args.a5_arm or _best_arm(rows)
    print(f"A5: re-running arm {best} paired on {aa.FLASH} vs {aa.PRO}")

    u = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    items, as_of = load_items(args.items)
    # The A5 subset is drawn the same shuffle-then-prefix way as the item set
    # itself, not alphabetically: `sorted(...)[:n]` would run the model tier on
    # the securities whose tickers begin with A, which is a universe chosen by
    # the letter A rather than a universe.
    _sub = sorted(items)
    random.Random(SEED + 5).shuffle(_sub)
    sub = sorted(_sub[:args.a5])
    peers = build_peers(u["snapshots"], {k: items[k] for k in sub})
    registry = aa.load_registry(REGISTRY)

    started = datetime.now(timezone.utc)
    made_at = started.isoformat(timespec="seconds")
    st = research_budget.check(aa.CAMPAIGN)
    spend0, calls0 = float(st.cost_usd or 0.0), int(st.n_calls or 0)

    cells = [(best, t, "", leg) for t in sub for leg in ("flash", "pro")]
    cells = [c for c in cells if f"{c[0]}|{c[1]}|{c[2]}|{c[3]}" not in done]
    random.Random(SEED).shuffle(cells)
    print(f"{len(cells)} A5 cells to run")
    ck = CHECKPOINT.open("a", encoding="utf-8")
    lock = threading.Lock()
    counts: Counter = Counter()
    halted = None

    def caller(messages, **kw):
        return aa.call_model(messages, since=None, **kw)

    def work(cell):
        arm, tkr, persona, leg = cell
        snap = items[tkr]
        model = aa.PRO if leg == "pro" else aa.FLASH
        kwargs: dict[str, Any] = {"caller": caller, "model": model}
        if arm == "A0":
            kwargs["persona"] = (personas_for(snap) or ["skeptic"])[0]
        if arm == "A4":
            kwargs["ctx"] = aa.ToolContext(snapshot=snap,
                                           peers=peers.get(tkr, []),
                                           registry=registry)
        return aa.RUNNERS[arm](snap, **kwargs), snap, leg

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, c): c for c in cells}
        try:
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    res, snap, leg = fut.result()
                except aa.ResearchBudgetExhausted as exc:
                    halted = str(exc)
                    break
                except Exception as exc:                  # noqa: BLE001
                    counts["failed"] += 1
                    log.warning("A5 cell crashed: %s", exc)
                    continue
                recs = (aa.mint(res, snapshot=snap, made_at=made_at)
                        if res.status == "ok" else [])
                if recs:
                    bs.append(recs)
                with lock:
                    counts[f"{leg}:{res.status}"] += 1
                    row = res.as_row()
                    row["arm"] = f"A5_{leg}"
                    row["leg"] = leg
                    row["base_arm"] = res.arm
                    row["prediction_ids"] = [r.prediction_id for r in recs]
                    ck.write(json.dumps(row, default=str) + "\n")
                    if i % 20 == 0:
                        ck.flush()
                        b = research_budget.check(aa.CAMPAIGN)
                        print(f"[{i}/{len(cells)}] {dict(counts)} "
                              f"${float(b.cost_usd or 0)-spend0:.3f}", flush=True)
        finally:
            ck.flush()
            ck.close()
    b = research_budget.check(aa.CAMPAIGN)
    print(f"A5 done: {dict(counts)} halted={halted} "
          f"spend ${float(b.cost_usd or 0.0)-spend0:.4f} over "
          f"{int(b.n_calls or 0)-calls0} calls")
    return 0


def _best_arm(rows: list[dict]) -> str:
    ranked = []
    for arm in aa.ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        if not rs:
            continue
        m = aa.arm_metrics(rs)
        if m["ideas_per_usd"] is not None:
            ranked.append((m["ideas_per_usd"], arm))
    ranked.sort(reverse=True)
    return ranked[0][1] if ranked else "A0"


# ── the report ──────────────────────────────────────────────────────────────

def analyse(rows: list[dict]) -> dict:
    """Every number the trial owes, computed once."""
    arms = sorted({r["arm"] for r in rows})
    by_arm = {a: [r for r in rows if r["arm"] == a] for a in arms}
    a0_rows = by_arm.get("A0", [])

    # A0 sliced to ONE persona per item: the same rows, read as the cheaper
    # architecture. Reported as a SENSITIVITY, never as the threshold, because
    # A0's registered identity is the multi-persona swarm that produced 0.2996.
    first_persona: dict[str, str] = {}
    a0_k1: list[dict] = []
    for r in sorted(a0_rows, key=lambda x: (x["item"], x.get("persona", ""))):
        if first_persona.setdefault(r["item"], r.get("persona", "")) == \
                r.get("persona", ""):
            a0_k1.append(r)

    metrics = {a: aa.arm_metrics(rs) for a, rs in by_arm.items()}
    metrics["A0_k1_sensitivity"] = aa.arm_metrics(a0_k1)
    boot = aa.bootstrap_a0_dispersion(a0_rows) if a0_rows else {}
    boot_k1 = aa.bootstrap_a0_dispersion(a0_k1) if a0_k1 else {}

    paired = {}
    for a, rs in by_arm.items():
        if a == "A0" or not a0_rows:
            continue
        paired[a] = aa.paired_difference(rs, a0_rows)

    # The §20 ratio computed the SWARM-1 way, so it can be read beside 0.2996.
    eff = {}
    for a, rs in by_arm.items():
        preds = [{"ticker": r["item"], **f}
                 for r in rs for f in (r.get("forecasts") or [])]
        eff[a] = aa.effective_distinct_ideas(preds)
    eff["A0_k1_sensitivity"] = aa.effective_distinct_ideas(
        [{"ticker": r["item"], **f} for r in a0_k1
         for f in (r.get("forecasts") or [])])

    rejects: dict[str, dict] = {}
    for a, rs in by_arm.items():
        c: Counter = Counter()
        for r in rs:
            for x in (r.get("rejections") or []):
                c[x["reason"]] += 1
        rejects[a] = dict(c.most_common())

    # Constraint 1, made checkable rather than asserted.
    served: dict[str, dict] = {}
    for a, rs in by_arm.items():
        c: Counter = Counter()
        for r in rs:
            for m in (r.get("served_models") or []):
                c[m] += 1
        served[a] = {"served_model_counts": dict(c),
                     "requested": sorted({m for r in rs for m in
                                          (r.get("requested_models") or [])}),
                     "n_alias_mismatch": sum(1 for r in rs
                                             if r.get("alias_mismatch"))}

    a2 = by_arm.get("A2", [])
    a2_extra = {}
    if a2:
        ups = [r["extra"].get("mean_abs_belief_update") for r in a2
               if (r.get("extra") or {}).get("mean_abs_belief_update") is not None]
        unch = sum(int((r.get("extra") or {}).get("n_posterior_equals_prior") or 0)
                   for r in a2)
        slots = sum(int((r.get("extra") or {}).get("n_matched_slots") or 0)
                    for r in a2)
        priors = [p for r in a2
                  for p in ((r.get("extra") or {}).get("prior_probabilities") or [])]
        a2_extra = {
            "n_cells_with_measurable_update": len(ups),
            "mean_abs_belief_update": (round(sum(ups) / len(ups), 4)
                                       if ups else None),
            "n_matched_slots": slots,
            "n_posterior_equals_prior": unch,
            "share_posterior_equals_prior": (round(unch / slots, 4)
                                             if slots else None),
            "n_priors_at_exactly_0.50": sum(1 for p in priors
                                            if abs(p - 0.5) < 1e-9),
            "n_priors": len(priors),
            "reading": ("`posterior == prior` is this arm's abstain channel; "
                        "its share is the honest analogue of the 27 "
                        "abstentions in 8,014 SWARM-1 calls"),
        }

    a3 = by_arm.get("A3", [])
    a3_extra = {}
    if a3:
        a3_extra = {
            "n_proposed": sum(int((r.get("extra") or {}).get("n_proposed") or 0)
                              for r in a3),
            "n_fatal_attacks": sum(
                int((r.get("extra") or {}).get("n_fatal_attacks") or 0)
                for r in a3),
            "n_killed_by_merge": sum(
                int((r.get("extra") or {}).get("n_killed_by_merge") or 0)
                for r in a3),
            "n_all_claims_killed": sum(
                1 for r in a3 for x in (r.get("rejections") or [])
                if x["reason"] == "all_claims_killed"),
        }

    a4 = by_arm.get("A4", [])
    a4_extra = {}
    if a4:
        tools: Counter = Counter()
        unavail: Counter = Counter()
        for r in a4:
            for t in (r.get("trace") or []):
                tools[t["tool"]] += 1
                if not t.get("available"):
                    unavail[t["tool"]] += 1
        rounds = [int((r.get("extra") or {}).get("n_tool_rounds") or 0)
                  for r in a4 if (r.get("extra") or {}).get("n_tool_rounds")
                  is not None]
        a4_extra = {
            "tool_call_counts": dict(tools.most_common()),
            "tool_unavailable_counts": dict(unavail.most_common()),
            "mean_tool_rounds": (round(sum(rounds) / len(rounds), 2)
                                 if rounds else None),
            "n_cells_that_asked_for_nothing": sum(
                1 for r in a4 if not (r.get("trace") or [])),
            "retrieval_mode": "FORWARD-ONLY, no web search, PIT tool layer",
        }

    return {"metrics": metrics, "bootstrap_a0": boot,
            "bootstrap_a0_k1": boot_k1, "paired": paired,
            "effective_distinct_ideas": eff, "rejections": rejects,
            "served_models": served, "a2": a2_extra, "a3": a3_extra,
            "a4": a4_extra,
            "arms_present": arms}


ARM_LABEL = {
    "A0": "A0 SNAPSHOT-PERSONA (control, corpse)",
    "A1": "A1 FINE-GRAINED (7 calls)",
    "A2": "A2 BELIEF-UPDATE (prior->posterior)",
    "A3": "A3 ADVERSARIAL (propose->refute->merge)",
    "A4": "A4 TOOL-CALL (forward-only)",
    "A5_flash": "A5 leg: deepseek-v4-flash",
    "A5_pro": "A5 leg: deepseek-v4-pro",
    "A0_k1_sensitivity": "A0 read at ONE persona per item (sensitivity)",
}


def write_report(rows: list[dict], meta: dict, leakage: dict) -> dict:
    a = analyse(rows)
    art = {
        "trial": aa.TRIAL, "module": aa.MODULE_VERSION,
        "prereg": r"Aegis module/TRIALS/PREREG_LLM_ARCHITECTURE_ARENA_1.md "
                  r"(frozen, commit 57cf834)",
        "run_meta": meta, "leakage_gate": leakage,
        "n_cells": len(rows), **a,
    }
    for m in art["metrics"].values():
        m.pop("_per_item_ideas", None)
        m.pop("_per_item_cost", None)
    ARTIFACT.write_text(json.dumps(art, indent=1, default=str),
                        encoding="utf-8")
    REPORT.write_text(_markdown(art), encoding="utf-8")
    print(f"wrote {REPORT} and {ARTIFACT}")
    return art


def _markdown(a: dict) -> str:
    m, boot, paired = a["metrics"], a["bootstrap_a0"], a["paired"]
    meta = a["run_meta"]
    L: list[str] = []
    L.append("# LLM-ARCHITECTURE-ARENA-1\n")
    L.append(f"**Prereg frozen at `{a['prereg']}`. Run "
             f"{meta.get('started_utc')} · observation timestamp "
             f"{meta.get('as_of')} · {meta.get('n_items')} paired items · "
             f"{meta.get('wall_clock_min')} min wall.**\n")
    L.append("_(narrative written by hand around these numbers; this file is "
             "regenerated by `scripts/run_architecture_arena_1.py "
             "--report-only`)_\n")
    L.append("## P1 — effective distinct ideas per dollar\n")
    L.append("| arm | items | calls | forecasts | eff. ideas | ratio | cost $ | "
             "**ideas/$** | $/idea | gradeable | abstain |\n"
             "|---|---|---|---|---|---|---|---|---|---|---|")
    for k in [x for x in ("A0", "A1", "A2", "A3", "A4", "A5_flash", "A5_pro",
                          "A0_k1_sensitivity") if x in m]:
        v = m[k]
        L.append(f"| {ARM_LABEL.get(k, k)} | {v['n_items']} | {v['n_calls']} | "
                 f"{v['n_forecasts']} | {v['effective_distinct_ideas']} | "
                 f"{v['ratio_ideas_per_forecast']} | {v['cost_usd']:.4f} | "
                 f"**{v['ideas_per_usd']}** | {v['cost_per_idea_usd']} | "
                 f"{v['gradeable_rate']} | {v['abstention_rate']} |")
    L.append("")
    if boot:
        L.append("### A0's own dispersion (the threshold, not a vibe)\n")
        L.append("```json\n" + json.dumps(boot, indent=1) + "\n```\n")
    if paired:
        L.append("### Paired per-item difference and its 80%-power MDE (§19)\n")
        L.append("| arm | n paired | mean (arm − A0) ideas/$ | MDE | t | "
                 "detectable |\n|---|---|---|---|---|---|")
        for k, v in sorted(paired.items()):
            if "mean_per_item_difference" not in v:
                L.append(f"| {k} | {v.get('n_paired_items')} | — | — | — | "
                         f"not estimable |")
                continue
            L.append(f"| {k} | {v['n_paired_items']} | "
                     f"{v['mean_per_item_difference']} | "
                     f"{v['mde_80pct_power']} | {v['t']} | "
                     f"{'YES' if v['detectable'] else 'NO'} |")
        L.append("")
    L.append("## Constraint 1 — served_model, read off every response body\n")
    L.append("```json\n" + json.dumps(a["served_models"], indent=1) + "\n```\n")
    L.append("## What each arm refused\n")
    L.append("```json\n" + json.dumps(a["rejections"], indent=1) + "\n```\n")
    L.append("## §20 ratios, comparable to SWARM-1's 0.2996\n")
    L.append("```json\n" + json.dumps(a["effective_distinct_ideas"], indent=1)
             + "\n```\n")
    for key, title in (("a2", "A2 — the belief update"),
                       ("a3", "A3 — what survived the refuter"),
                       ("a4", "A4 — the tool trace")):
        if a.get(key):
            L.append(f"## {title}\n")
            L.append("```json\n" + json.dumps(a[key], indent=1) + "\n```\n")
    L.append("## Leakage gate on P2\n")
    L.append("```json\n" + json.dumps(a["leakage_gate"], indent=1) + "\n```\n")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=int, default=120)
    ap.add_argument("--pilot", type=int, default=None,
                    help="run only this many ITEMS, to measure before spending")
    ap.add_argument("--arms", default=None, help="comma list, default all")
    ap.add_argument("--a0-persona-cap", type=int, default=None,
                    help="cap A0's personas per item (default: SWARM-1 routing)")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--a5", type=int, default=0,
                    help="run the A5 model-tier leg on this many items")
    ap.add_argument("--a5-arm", default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    if args.report_only:
        rows, _ = load_checkpoint()
        meta = (json.loads(RUN_META.read_text(encoding="utf-8"))
                if RUN_META.exists() else {})
        leak_path = RUN_DIR / "leakage_gate.json"
        leakage = (json.loads(leak_path.read_text(encoding="utf-8"))
                   if leak_path.exists()
                   else {"status": "NOT RECORDED",
                         "reading": "P2 is withheld: the leakage gate was never "
                                    "written, and an ungated P2 would be a "
                                    "number nobody checked"})
        write_report(rows, meta, leakage)
        return 0
    if args.a5:
        return run_a5(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
