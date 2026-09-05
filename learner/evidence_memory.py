"""EVIDENCE MEMORY -- what a weekend of passes is allowed to conclude.

THE PROBLEM THIS SOLVES
=======================
A looping lab produces the same shaped receipt over and over. Without a memory,
pass 19 knows nothing that pass 1 knew, the leaderboard is a LOG rather than a
state, and the only way to read forty hours of work is to read forty hours of
work. Worse, it makes both errors available at once:

* a cell that happened to look good on ONE pass gets quoted as a finding, and
* a cell that happened to look flat on ONE pass gets called dead.

THE RULE THAT PREVENTS BOTH: **A SINGLE PASS CAN NEITHER PROMOTE NOR KILL.**
Every state transition here needs at least two independent passes agreeing, and
`REFUTED` needs three AND needs each of them to have had the POWER to detect the
effect. That last clause is the one that is usually missing, and it is the
difference between "we looked and it was not there" and "we looked with an
instrument too short to see it". The night lab of 2026-09-05 produced exactly
that situation -- a +14.4%/yr arm needing 16.1 years to resolve on 7 years of
tape -- and reporting it as NOISE would have been a false negative dressed as
rigour.

THE STATES, AND WHAT EACH ONE LICENSES
======================================
| state | means | may it be traded? |
|---|---|---|
| `IDEA` | fewer than 2 passes. Nothing is known yet. | no |
| `CONDITIONAL` | clears its bar repeatedly, not the full NOVEL bar | paper only |
| `SUPPORTED` | clears DSR + SPA + PBO + 2-of-3 eras, twice | candidate |
| `REGIME_SPECIFIC` | real in ONE era, absent in the others | paper, scoped |
| `COST_KILLED` | beats the market GROSS, loses NET | no -- fix the costs |
| `REFUTED` | 3+ POWERED passes, none positive | no |

`COST_KILLED` is a separate state on purpose. "It does not work" and "it works
and the spread eats it" call for completely different next moves -- the second
one is an execution problem, and collapsing it into REFUTED throws away a live
lead. This repo has killed several ideas that were only ever the second kind.

THE ESTIMATOR IS NOT NEW
========================
The shrinkage comes from `backend/services/arena/trust_router.backoff_estimate`,
re-keyed from (actor, context) to (family, cell). A thin cell inherits its
family's rate instead of shouting alone, which is the same reason that estimator
exists on the arena side: a leaf with two observations and a 100% hit rate is
not a 100% hit rate. Re-using it rather than writing a second shrinkage rule
means the two halves of the system cannot disagree about what thin evidence is
worth.

APPEND-ONLY, JSONL, ON PURPOSE
==============================
Every observation is appended and nothing is ever rewritten, so the state is
always DERIVED from the full history and can be recomputed under a different
rule later. A store that overwrites its own summary cannot answer "what did we
believe before we changed the bar", which is the question every retrospective
actually asks. It is greppable, diffable, and survives a killed job with
everything written up to that moment intact.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STORE_DIR = REPO / "backend" / "data" / "optimus" / "learner"
STORE = STORE_DIR / "evidence_memory.jsonl"
STATE_SNAPSHOT = STORE_DIR / "evidence_memory_state.json"

VERSION = "evidence-memory-1"

STATES = ("IDEA", "CONDITIONAL", "SUPPORTED", "REGIME_SPECIFIC",
          "COST_KILLED", "REFUTED")

#: A pass "clears the bar" when it would have been called NOVEL on its own.
DSR_BAR = 0.95
SPA_BAR = 0.10
PBO_BAR = 0.5

#: A single pass can neither promote nor kill.
MIN_PASSES_TO_PROMOTE = 2
MIN_PASSES_TO_REFUTE = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ recording

def observe(family_id: str, cell: str, *, n_months, sharpe=None, dsr=None,
            spa_p=None, pbo=None, verdict=None, powered=None,
            years_needed_for_t2=None, years_observed=None,
            eras=None, gross_beats_market=None, net_beats_market=None,
            job=None, run=None, variant=None, note=None) -> dict:
    """Append ONE observation. Never updates, never dedupes, never overwrites."""
    row = {
        "utc": _now(), "version": VERSION,
        "family_id": family_id, "cell": cell,
        "job": job, "run": run, "variant": variant,
        "n_months": n_months, "sharpe": sharpe,
        "dsr": dsr, "spa_p": spa_p, "pbo": pbo,
        "verdict": verdict,
        "powered": powered,
        "years_needed_for_t2": years_needed_for_t2,
        "years_observed": years_observed,
        "eras": eras,
        "gross_beats_market": gross_beats_market,
        "net_beats_market": net_beats_market,
        "note": note,
    }
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    with STORE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


def read_all() -> list[dict]:
    if not STORE.exists():
        return []
    out = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ------------------------------------------------------------------- scoring

def _clears(r: dict) -> bool:
    """Would this ONE pass have been called NOVEL on its own?"""
    dsr, spa_p, pbo = r.get("dsr"), r.get("spa_p"), r.get("pbo")
    if not isinstance(dsr, (int, float)) or not isinstance(spa_p, (int, float)):
        return False
    if dsr < DSR_BAR or spa_p > SPA_BAR:
        return False
    if isinstance(pbo, (int, float)) and pbo >= PBO_BAR:
        return False
    eras = r.get("eras") or {}
    return bool(eras.get("holds_in_2_of_3") or eras.get("same_sign_in_2_of_3"))


def _era_count(r: dict) -> tuple[int, int]:
    eras = r.get("eras") or {}
    pos = eras.get("eras_with_a_positive_mean")
    meas = eras.get("eras_measured")
    return (int(pos) if isinstance(pos, int) else 0,
            int(meas) if isinstance(meas, int) else 0)


def state_of(rows: list[dict], family_rate: float | None = None,
             global_rate: float | None = None) -> dict:
    """The state of ONE cell, from every observation of it.

    Order matters and is deliberate: COST_KILLED is checked BEFORE REFUTED,
    because a cell that beats the market gross and loses net is an execution
    problem wearing a research failure's clothes, and calling it REFUTED closes
    a live lead.
    """
    from backend.services.arena import trust_router as TR
    n = len(rows)
    if n == 0:
        return {"state": "IDEA", "passes": 0, "why": "never observed"}
    cleared = sum(1 for r in rows if _clears(r))
    powered = [r for r in rows if r.get("powered") is True]
    n_powered = len(powered)
    cost_killed = [r for r in rows
                   if r.get("gross_beats_market") is True
                   and r.get("net_beats_market") is False]
    # Shrunk hit rate: global -> family -> this cell. A leaf with 2 of 2 is not
    # a 100% rate, and the hierarchy is what says so.
    levels = []
    if global_rate is not None:
        levels.append((global_rate * 100.0, 100.0))
    if family_rate is not None:
        levels.append((family_rate * 50.0, 50.0))
    levels.append((float(cleared), float(n)))
    est = TR.backoff_estimate(levels, prior=0.10)

    regime = 0
    for r in rows:
        pos, meas = _era_count(r)
        if meas >= 3 and pos == 1:
            regime += 1

    if n < MIN_PASSES_TO_PROMOTE:
        state, why = "IDEA", f"only {n} pass; a single pass can neither promote nor kill"
    elif cleared >= MIN_PASSES_TO_PROMOTE:
        state, why = "SUPPORTED", f"cleared the full bar on {cleared} of {n} passes"
    elif len(cost_killed) >= MIN_PASSES_TO_PROMOTE:
        state, why = ("COST_KILLED",
                      f"beat the market GROSS and lost NET on {len(cost_killed)} of {n} "
                      "passes -- an execution problem, not a research failure")
    elif regime >= MIN_PASSES_TO_PROMOTE:
        state, why = ("REGIME_SPECIFIC",
                      f"positive in exactly one of three eras on {regime} of {n} passes")
    elif cleared >= 1:
        state, why = "CONDITIONAL", f"cleared the bar on {cleared} of {n} passes, not twice"
    elif n_powered >= MIN_PASSES_TO_REFUTE:
        state, why = ("REFUTED",
                      f"{n_powered} POWERED passes and none cleared the bar")
    else:
        # THE CLAUSE THAT IS USUALLY MISSING. Without power, "we looked and found
        # nothing" is not evidence of absence, and calling it REFUTED would be a
        # false negative wearing rigour's clothes.
        need = [r.get("years_needed_for_t2") for r in rows
                if isinstance(r.get("years_needed_for_t2"), (int, float))]
        state = "IDEA"
        why = (f"{n} passes, none cleared the bar, but only {n_powered} had the POWER to "
               f"detect it"
               + (f" (a t = 2 would need up to {max(need):.1f} years)" if need else "")
               + " -- absence of evidence is not evidence of absence")
    return {
        "state": state, "why": why,
        "passes": n, "passes_clearing_the_bar": cleared,
        "powered_passes": n_powered,
        "cost_killed_passes": len(cost_killed),
        "one_era_only_passes": regime,
        "shrunk_clear_rate": round(float(est["estimate"]), 4),
        "evidence_n": est["evidence_n"],
        "last_seen": rows[-1].get("utc"),
        "best_dsr": max((r["dsr"] for r in rows
                         if isinstance(r.get("dsr"), (int, float))), default=None),
        "median_n_months": sorted(
            [r["n_months"] for r in rows if isinstance(r.get("n_months"), int)]
        )[len(rows) // 2] if any(isinstance(r.get("n_months"), int) for r in rows) else None,
    }


def snapshot() -> dict:
    """Every cell's state, derived from the whole history. Written to disk."""
    rows = read_all()
    by_cell: dict[tuple[str, str], list[dict]] = {}
    by_family: dict[str, list[dict]] = {}
    for r in rows:
        by_cell.setdefault((r.get("family_id"), r.get("cell")), []).append(r)
        by_family.setdefault(r.get("family_id"), []).append(r)
    g_clear = (sum(1 for r in rows if _clears(r)) / len(rows)) if rows else 0.0
    fam_rate = {f: (sum(1 for r in rs if _clears(r)) / len(rs)) if rs else 0.0
                for f, rs in by_family.items()}
    cells = {}
    for (fam, cell), rs in by_cell.items():
        cells[f"{fam}::{cell}"] = state_of(rs, family_rate=fam_rate.get(fam),
                                           global_rate=g_clear)
    counts: dict[str, int] = {}
    for v in cells.values():
        counts[v["state"]] = counts.get(v["state"], 0) + 1
    out = {
        "version": VERSION, "written_utc": _now(),
        "observations": len(rows),
        "cells": len(cells),
        "families": sorted(by_family),
        "global_clear_rate": round(g_clear, 4),
        "state_counts": counts,
        "rule": ("a single pass can neither promote nor kill; REFUTED additionally "
                 f"requires {MIN_PASSES_TO_REFUTE} passes that each HAD THE POWER "
                 "to detect the effect"),
        "by_cell": dict(sorted(cells.items(),
                               key=lambda kv: -(kv[1].get("best_dsr") or 0))),
    }
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_SNAPSHOT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out


def record_receipt(payload: dict) -> int:
    """Fold one weekend-lab receipt into the memory. Returns rows written.

    Reads the receipt's OWN cells where it has them, so a grid of 32 cells
    contributes 32 observations rather than one -- the family is the unit the
    multiplicity tests already work in, and the memory has to agree with them.
    """
    fam = payload.get("family_id")
    if not fam:
        return 0
    inf = payload.get("inference") or {}
    power = inf.get("power") or {}
    eras = payload.get("era_sign_table")
    cells = payload.get("cells") or {}
    best = payload.get("best_cell")
    written = 0
    for cell, book in cells.items():
        if not isinstance(book, dict) or "error" in book:
            continue
        tw_net = book.get("terminal_wealth_net")
        tw_gross = book.get("terminal_wealth_gross")
        tw_mkt = book.get("terminal_wealth_market_same_months")
        is_best = (cell == best)
        observe(
            fam, cell,
            n_months=book.get("months"),
            sharpe=None,
            # Only the BEST cell carries the family-level inference: the DSR,
            # SPA and PBO were computed FOR the family maximum, and pasting them
            # onto every cell would let a mediocre cell inherit the champion's
            # correction.
            dsr=(inf.get("deflated_sharpe") or {}).get("dsr") if is_best else None,
            spa_p=(inf.get("spa") or {}).get("p_spa_consistent") if is_best else None,
            pbo=(inf.get("pbo") or {}).get("pbo") if is_best else None,
            verdict=payload.get("verdict") if is_best else None,
            powered=power.get("powered") if is_best else None,
            years_needed_for_t2=power.get("years_needed_for_t2") if is_best else None,
            years_observed=power.get("years_observed") if is_best else None,
            eras=eras if is_best else None,
            gross_beats_market=(None if tw_gross is None or tw_mkt is None
                                else bool(tw_gross > tw_mkt)),
            net_beats_market=(None if tw_net is None or tw_mkt is None
                              else bool(tw_net > tw_mkt)),
            job=payload.get("job"), run=payload.get("run"),
            variant=payload.get("variant"),
            note=("family maximum -- carries the family's inference"
                  if is_best else "family member -- book only"),
        )
        written += 1
    return written


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="evidence memory")
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--ingest-dir", help="fold every *.json receipt in a directory")
    a = ap.parse_args(argv)
    if a.ingest_dir:
        n = 0
        for p in sorted(Path(a.ingest_dir).glob("*.json")):
            try:
                n += record_receipt(json.loads(p.read_text(encoding="utf-8")))
            except Exception as exc:                                    # noqa: BLE001
                print(f"  {p.name}: {type(exc).__name__}: {exc}")
        print(f"folded {n} cell observations")
    s = snapshot()
    print(json.dumps({k: v for k, v in s.items() if k != "by_cell"}, indent=1))
    for k, v in list(s["by_cell"].items())[:15]:
        print(f"  {v['state']:<16} {k[:80]}  ({v['why'][:70]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
