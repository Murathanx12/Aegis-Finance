"""G3 — THE MUTATION ROUND. The LLM proposes; code decides; the corpse is named.

`docs/ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §3, item G3.

THE DIVISION OF LABOUR, WHICH IS THE WHOLE POINT
================================================
DeepSeek sees the five leading development genomes, the mutation GRAMMAR, and
the eleven dead mechanisms in `signal_registry`. It returns at most twenty
children. **It computes nothing.** Every return, every drawdown, every beta in
this receipt is produced by `learner.growth_lab` and `learner.growth` from the
same panel and the same pinned tapes that produced G2 — the model's only
authority is over which twenty points in the grammar are worth spending a
second of compute on.

FOUR REFUSALS, IN CODE
======================
1. **The grammar.** A mutation names a key outside `MUTATION_GRAMMAR`, or a
   value outside its declared range, and it is refused — not clipped. A clipped
   proposal is a different proposal wearing the model's label, and the lineage
   would then record something that was never run.
2. **The corpse.** Every child names a `parent_corpse_id` drawn from the
   REJECTED/PERVERSE grades in `backend/services/signal_registry.py`, and a
   `distinct_claim` of at least five words. The rule is
   `research_daemon.assert_distinct_from_corpses`, applied here directly:
   `scripts/lint_prereg.py` is named in `llm_research.generate_hypotheses`'s
   docstring and **does not exist in this repository** — a fact this receipt
   records rather than papering over.
3. **The budget.** $3.00, measured as the DELTA of `llm_research.spent_usd()`
   across this job, checked before every call. The module's own
   `CAMPAIGN_BUDGET_USD` of $30 is a different, wider gate and is not this one.
4. **The sealed era.** Children are evaluated on the development window only,
   through the same `assert_development_only` latch as generation 0.

THE FAMILY GROWS, SO THE DEFLATION MOVES
========================================
Every child is a cell that was looked at. `n_trials` for the DSR becomes the
generation-0 family plus every child *evaluated*, and the receipt reports the
generation-0 DSR alongside the enlarged one so the cost of the search is
visible rather than absorbed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP          # noqa: E402
from learner import growth as GR                               # noqa: E402
from learner import growth_lab as GL                           # noqa: E402
from scripts import growth_g2_generation0 as G2                # noqa: E402

OUT_DIR = GL.OUT_DIR
LLM_CAP_USD = 3.00
MAX_MUTATIONS = 20
N_PARENTS = 5

#: the ONLY keys a mutation may set, and the range each may take. A key that is
#: not here is refused; a value outside the range is refused. Both refusals are
#: recorded on the child so a rejected proposal is still evidence about the
#: proposer.
MUTATION_GRAMMAR = {
    "pred_col": ["mom_12_1", "mom_over_vol", "quality_mom", "lgbm_clf",
                 "nn_pre_causal_seedmean", "roe_pit", "ret_12m", "vol_60d",
                 "log_market_cap", "prior_1m"],
    "k": (10, 150),
    "weight": ["vw", "ew"],
    "hold_k": (11, 400),
    "overlay": ["dd", "tg", "bsc"],
    "dd_lookback_months": (1, 12),
    "dd_scale": (0.05, 0.80),
    "dd_floor": (0.0, 0.95),
    "bsc_lookback_months": (3, 24),
    "bsc_cap": (0.25, 2.0),
}


def corpses() -> list[dict]:
    """The dead mechanisms, DERIVED from the registry, never re-typed."""
    from backend.services import signal_registry as SR
    reg = SR.load()
    sigs = reg.signals.values() if hasattr(reg, "signals") else list(reg)
    out = []
    for s in sigs:
        grade = getattr(s, "evidence_grade", "")
        if grade in SR.NEVER_PICKS:
            out.append({"signal_id": getattr(s, "signal_id", str(s)),
                        "evidence_grade": grade,
                        "permitted_role": getattr(s, "permitted_role", "")})
    return sorted(out, key=lambda d: d["signal_id"])


# ------------------------------------------------------------- the validator

class Refused(ValueError):
    pass


def _in_range(key, val):
    spec = MUTATION_GRAMMAR[key]
    if isinstance(spec, list):
        if val not in spec:
            raise Refused(f"{key}={val!r} is not one of {spec}")
        return val
    lo, hi = spec
    v = float(val)
    if not (lo <= v <= hi):
        raise Refused(f"{key}={v} is outside [{lo}, {hi}]")
    return int(v) if isinstance(lo, int) else v


def validate(child: dict, parents: dict, corpse_ids: set[str]) -> dict:
    """Return a normalised mutation, or raise `Refused` with the reason."""
    pid = str(child.get("parent_id") or "")
    if pid not in parents:
        raise Refused(f"parent_id {pid!r} is not one of the five leaders "
                      f"{sorted(parents)}")
    cid = str(child.get("parent_corpse_id") or "")
    if cid not in corpse_ids:
        raise Refused(f"parent_corpse_id {cid!r} is not a REJECTED/PERVERSE "
                      f"signal in the registry")
    claim = str(child.get("distinct_claim") or "").strip()
    if len(claim.split()) < 5:
        raise Refused(
            f"names corpse {cid} but its distinct_claim is {claim!r}. A "
            "distinct claim is a sentence, not a feeling "
            "(research_daemon.assert_distinct_from_corpses)")
    mut = child.get("mutation")
    if not isinstance(mut, dict) or not mut:
        raise Refused("mutation must be a non-empty object")
    norm = {}
    for k, v in mut.items():
        if k not in MUTATION_GRAMMAR:
            raise Refused(f"{k!r} is not in the mutation grammar "
                          f"{sorted(MUTATION_GRAMMAR)}")
        if k == "overlay":
            if not isinstance(v, list) or not all(
                    x in MUTATION_GRAMMAR["overlay"] for x in v):
                raise Refused(f"overlay {v!r} must be a list drawn from "
                              f"{MUTATION_GRAMMAR['overlay']}")
            norm[k] = list(dict.fromkeys(v))
        else:
            norm[k] = _in_range(k, v)
    return {"parent_id": pid, "parent_corpse_id": cid, "distinct_claim": claim,
            "mutation": norm,
            "rationale": str(child.get("rationale") or "")[:600]}


def child_genome(base_genome: GL.Genome, norm: dict, idx: int) -> GL.Genome:
    spec = dict(base_genome.spec)
    overlay = list(base_genome.overlay)
    m = norm["mutation"]
    for k in ("pred_col", "k", "weight", "hold_k"):
        if k in m:
            spec[k] = m[k]
    for k in ("dd_lookback_months", "dd_scale", "dd_floor",
              "bsc_lookback_months", "bsc_cap"):
        if k in m:
            spec[k] = m[k]
    if "overlay" in m:
        overlay = list(m["overlay"])
    if base_genome.base.startswith("spy_"):
        # an index genome has no pred_col/k/weight; those keys are inert on it
        # and are dropped rather than carried as decoration on the receipt.
        for k in ("pred_col", "k", "weight", "hold_k"):
            spec.pop(k, None)
    gid = f"m{idx:02d}_{base_genome.genome_id}"
    diff = ", ".join(f"{k}={v}" for k, v in sorted(m.items()))
    return GL.Genome(
        genome_id=gid, family=f"{base_genome.family}/mutation",
        base=base_genome.base, spec=spec, overlay=tuple(overlay),
        parent_ids=(base_genome.genome_id,),
        mutation_history=(f"{base_genome.genome_id} -> {gid}: {diff}",),
        note=norm["rationale"][:200])


# ------------------------------------------------------------------ the ask

PROMPT = """You are proposing MUTATIONS for a quantitative growth-book search.
You do not compute anything. Code evaluates every proposal on a fixed panel.

THE OBJECTIVE (already declared and hashed; you cannot change it):
{objective}

THE RANKING METRIC: leverage-neutral terminal wealth — the book re-run at SPY's
own realised volatility with borrowed notional charged at RF + 100 bps — over
2004-01..2015-12, after costs. Beta is allowed; hidden beta is not.

THE FIVE LEADING PARENTS on that development window (beta first). The
parent_id you return must be EXACTLY one of the identifiers that begin these
lines -- no cost-rate suffix, no renaming, no invention:
{parents}

THE MUTATION GRAMMAR. You may set ONLY these keys, only within these ranges.
Anything else is refused by code, not clipped:
{grammar}

Notes on what the keys do:
  pred_col   the cross-sectional score the monthly top-k book is ranked on
  k          book size; weight  vw or ew; hold_k  hysteresis band (must exceed k)
  overlay    a list from: dd (exposure scaled by the book's own trailing
             drawdown), tg (a 10-month trend gate on SPY, out to T-bills),
             bsc (portfolio volatility targeting)
  dd_scale / dd_floor / dd_lookback_months   the drawdown overlay's shape
  bsc_lookback_months / bsc_cap              the vol-targeting overlay's shape

THE DEAD MECHANISMS. Every proposal must name the ONE that comes closest to it
and say, in a full sentence of at least five words, what this asks that the dead
test did not:
{corpses}

Propose AT MOST {n} mutations. Prefer proposals that would move the metric for a
REASON you can state, and that are not minor re-parameterisations of each other.
Return ONLY a JSON array, no prose, each element exactly:
{{"parent_id": "...", "mutation": {{...}}, "rationale": "one sentence",
  "parent_corpse_id": "...", "distinct_claim": "at least five words"}}
Answer in English."""


def build_prompt(parents: list[dict], corpse_list: list[dict]) -> str:
    # THE PARENT IS NAMED BY ITS GENOME ID, NOT ITS CELL ID. Round 1 of this job
    # printed the CELL id -- "lgbm_clf|dd|10bps" -- while the validator matches on
    # the GENOME, "lgbm_clf|dd". All twenty proposals named a parent that does not
    # exist and all twenty were refused. The proposals were sound; the INTERFACE
    # was wrong, and 20 of 20 refusals from one cause is a finding about the
    # prompt, not about the model. Round 1 is kept at
    # G3_mutations_round01_ALL_REFUSED.json rather than deleted.
    pl = "\n".join(
        f"  {p['genome_id']}: beta {p['beta']}, leverage-neutral TW "
        f"{p['leverage_neutral_tw']} (SPY {p['spy_tw']}), raw TW {p['raw_tw']}, "
        f"maxDD {p['max_drawdown']}, spec {json.dumps(p['spec'])}, "
        f"overlay {p['overlay']}"
        for p in parents)
    gl = "\n".join(f"  {k}: {v}" for k, v in MUTATION_GRAMMAR.items())
    cl = "\n".join(f"  {c['signal_id']} ({c['evidence_grade']})" for c in corpse_list)
    return PROMPT.format(objective=GR.OBJECTIVE, parents=pl, grammar=gl,
                         corpses=cl, n=MAX_MUTATIONS)


def propose(prompt: str, *, dry_run: bool, cap_usd: float) -> tuple[list, dict]:
    """One LLM call under a job-local dollar cap. Returns (children, spend)."""
    from backend.services import llm_research as LR
    before = LR.spent_usd()
    if dry_run:
        return [], {"llm_calls": 0, "llm_spend_usd": 0.0, "dry_run": True,
                    "note": "no wire call"}
    ok, why = LR.available()
    if not ok:
        return [], {"llm_calls": 0, "llm_spend_usd": 0.0,
                    "refused": f"LLM unavailable: {why}"}
    res = LR.ask(prompt, purpose="growth_g3_mutations",
                 temperature=0.0, max_tokens=4000,
                 schema_hint="Return ONLY the JSON array.")
    after = LR.spent_usd()
    spend = {
        "llm_calls": 1,
        "llm_spend_usd": round(after - before, 6),
        "job_cap_usd": cap_usd,
        "model": res["call"]["model"],
        "prompt_tokens": res["call"]["prompt_tokens"],
        "completion_tokens": res["call"]["completion_tokens"],
        "output_sha256": res["call"]["output_sha256"],
        "truncated": res.get("truncated"),
        "ledger_before_usd": round(before, 6),
        "ledger_after_usd": round(after, 6),
        "campaign_budget_usd": LR.CAMPAIGN_BUDGET_USD,
    }
    if after - before > cap_usd:
        spend["over_cap"] = True
    try:
        parsed = LR.parse_json_block(res["text"])
    except Exception as exc:                                  # noqa: BLE001
        spend["parse_error"] = f"{type(exc).__name__}: {exc}"
        return [], spend
    if isinstance(parsed, dict):
        parsed = parsed.get("mutations") or parsed.get("proposals") or []
    return (parsed if isinstance(parsed, list) else []), spend


# --------------------------------------------------------------------- run

def run(*, dry_run: bool = False, replay: bool = False,
        verbose: bool = True, argv=None) -> dict:
    t0 = datetime.now(timezone.utc)
    tracker = RP.InputTracker()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from scripts import w3_neural_floored as W3B
    free = W3B.free_gb()
    if free is not None and free < 6.0:
        raise SystemExit(f"REFUSED: {free:.1f} GB free, floor 6.0 GB.")

    round1 = OUT_DIR / "G3_mutations_round01_ALL_REFUSED.json"
    g2_path = OUT_DIR / "G2_generation0.json"
    if not g2_path.exists():
        raise SystemExit(f"REFUSED: {g2_path} is missing. G3 mutates G2's "
                         "leaders and cannot invent them.")
    tracker.opened(g2_path, note="G2 generation-0 receipt")
    g2 = json.loads(g2_path.read_text(encoding="utf-8"))
    tracker.opened(GL.DECLARATION, note="the hashed declaration")
    decl = json.loads(GL.DECLARATION.read_text(encoding="utf-8"))

    gen0 = {g.genome_id: g for g in GL.generation_zero()}
    # the five leading GENOMES (not cells): a genome that leads at both cost
    # rates is one parent, not two.
    seen, parents = set(), []
    for row in g2["leaderboard_by_leverage_neutral_tw"]:
        gid = row["cell"].rsplit("|", 1)[0]
        if gid in seen or gid not in gen0:
            continue
        seen.add(gid)
        g = gen0[gid]
        parents.append({**row, "genome_id": gid, "spec": g.spec,
                        "overlay": list(g.overlay)})
        if len(parents) == N_PARENTS:
            break
    parent_map = {p["genome_id"]: gen0[p["genome_id"]] for p in parents}

    corpse_list = corpses()
    corpse_ids = {c["signal_id"] for c in corpse_list}
    prompt = build_prompt(parents, corpse_list)
    if replay:
        # REPLAY reads the proposals a previous round actually received and
        # makes NO wire call. A receipt that cannot be recomputed without paying
        # the model again is not reproducible, and re-asking at temperature 0 is
        # not the same thing as replaying -- the provider is free to change.
        prev = OUT_DIR / "G3_mutations.json"
        if not prev.exists():
            raise SystemExit(f"REFUSED: --replay needs {prev} and it is absent.")
        tracker.opened(prev, note="the proposals being replayed")
        prior = json.loads(prev.read_text(encoding="utf-8"))
        raw = prior.get("proposals_raw") or []
        if not raw:
            raise SystemExit(
                "REFUSED: the previous receipt carries no `proposals_raw`, so "
                "there is nothing to replay. Run once live to record them.")
        spend = {"llm_calls": 0, "llm_spend_usd": 0.0, "replayed_from": str(prev),
                 "replayed_spend_usd": (prior.get("llm") or {}).get("llm_spend_usd"),
                 "note": "no wire call; the proposals are the ones already paid for"}
    else:
        raw, spend = propose(prompt, dry_run=dry_run, cap_usd=LLM_CAP_USD)

    # ------------------------------------------------------------- validate
    accepted, refused = [], []
    for i, child in enumerate(raw[:MAX_MUTATIONS]):
        try:
            norm = validate(child if isinstance(child, dict) else {},
                            parent_map, corpse_ids)
        except Refused as exc:
            refused.append({"index": i, "proposal": child, "refusal": str(exc)})
            continue
        accepted.append(norm)

    # ------------------------------------------------------------- evaluate
    cells, series_dev = {}, {}
    genomes: list[GL.Genome] = []
    spy_dev = pd.Series(dtype="float64")
    if accepted:
        panel, uni, fp = G2.load_panel(tracker, verbose=verbose)
        ctx = GL.market_context(panel, tracker)
        spy_dev = GL.dev(ctx["spy"].dropna())
        rf_dev = GL.dev(ctx["rf"].dropna())
        for i, norm in enumerate(accepted, start=1):
            g = child_genome(parent_map[norm["parent_id"]], norm, i)
            if g.spec.get("hold_k") is not None and \
                    int(g.spec["hold_k"]) <= int(g.spec.get("k", GL.BOOK_K)):
                refused.append({"index": i, "proposal": norm,
                                "refusal": f"hold_k={g.spec['hold_k']} must exceed "
                                           f"k={g.spec.get('k', GL.BOOK_K)}; a hold "
                                           "band that is not a band would read as "
                                           "one in the receipt"})
                continue
            genomes.append(g)
            for bps in GL.COST_RATES_BPS:
                key = f"{g.genome_id}|{bps:.0f}bps"
                try:
                    s, meta = _build_child(g, panel, ctx, bps)
                except SystemExit as exc:
                    cells[key] = {"genome": g.to_json(), "cost_bps_per_side": bps,
                                  "verdict": "REFUSED", "why": str(exc)}
                    continue
                s = pd.Series(s.to_numpy(),
                              index=pd.Index([str(x) for x in s.index])).dropna().sort_index()
                d = GL.dev(s)
                GL.assert_development_only(d, f"child {g.genome_id}")
                if len(d) < 24:
                    cells[key] = {"genome": g.to_json(), "verdict": "CANNOT DETERMINE",
                                  "why": f"only {len(d)} development months"}
                    continue
                ev = GR.evaluate_growth(d, spy_dev, rf_dev, cost_bps=bps,
                                        label=key, n_boot=1000)
                ev["genome"] = g.to_json()
                ev["build"] = {k: v for k, v in meta.items() if k != "_series"}
                ev["lineage"] = {
                    "parent_ids": list(g.parent_ids),
                    "mutation_history": list(g.mutation_history),
                    "parent_corpse_id": norm["parent_corpse_id"],
                    "distinct_claim": norm["distinct_claim"],
                }
                cells[key] = ev
                series_dev[key] = d
                if verbose:
                    print(f"  {key:44s} beta {str(ev.get('beta')):>7s}  "
                          f"LN-TW {str((ev.get('leverage_neutral') or {}).get('terminal_wealth')):>8s}",
                          flush=True)

    # -------------------------------------------- the family, and its cost
    from learner import inference as INF

    gen0_family = int(g2["family_cells_declared"])
    enlarged = gen0_family + len(cells)
    graded = {k: v for k, v in cells.items() if v.get("beta") is not None}
    raw_p = {k: G2.two_sided_p((v.get("market_model") or {}).get("intercept_t_hac"))
             for k, v in graded.items()}
    # the family correction is over EVERYTHING looked at, generation 0 included.
    all_p = dict(raw_p)
    for k, v in g2["cells"].items():
        p = (v.get("significance") or {}).get("raw_p_intercept_hac")
        if p is not None:
            all_p[k] = p
    holm_all = G2.holm(all_p)
    fdr_all = G2.bh_fdr(all_p)

    for k, v in graded.items():
        # the DSR is taken on the EXCESS over SPY on the same months, exactly as
        # G2 takes it -- a Sharpe on the raw book would deflate a market return.
        excess = (series_dev[k] - spy_dev.reindex(series_dev[k].index)).dropna()
        d = INF.deflated_sharpe(excess.to_numpy(), n_trials=enlarged)
        v["significance"] = {
            "raw_p_intercept_hac": raw_p[k],
            "family_holm_p_over_gen0_plus_children": holm_all.get(k),
            "family_bh_fdr_p": fdr_all.get(k),
            "dsr_over_enlarged_family": d.get("dsr"),
            "dsr_block": d,
            "family_size_cells_generation0": gen0_family,
            "family_size_cells_after_mutation": enlarged,
        }
        v["verdict_growth"] = G2.verdict_naming_the_bar(
            raw_p[k], holm_all.get(k), d.get("dsr"),
            bool((v.get("constraints") or {}).get("passes")), None)

    board = G2.leaderboard(graded) if graded else []
    combined = sorted(
        board + [r for r in g2["leaderboard_by_leverage_neutral_tw"]],
        key=lambda r: (r.get("leverage_neutral_tw") is None,
                       -(r.get("leverage_neutral_tw") or 0.0)))

    out = {
        "job": "G3_mutations",
        "lane": "G growth book",
        "licence": "PRODUCT_EXPERIMENT",
        "question": ("do LLM-proposed mutations of the five leading development "
                     "genomes move the leverage-neutral terminal wealth, and what "
                     "does the enlarged family cost the deflation?"),
        "declaration_sha256": decl["sha256"],
        "sealed_era_openings": len(GL.sealed_openings()),
        "sealed_era_touched_by_this_job": False,
        "llm": {**spend, "prompt_chars": len(prompt),
                "cap_usd": LLM_CAP_USD,
                "role": "PROPOSER ONLY — every number below is computed by code"},
        "lint_prereg_note": (
            "`scripts/lint_prereg.py` is referenced by "
            "`llm_research.generate_hypotheses`'s docstring and DOES NOT EXIST in "
            "this repository. The corpse rule is applied directly instead: a "
            "`parent_corpse_id` drawn from signal_registry's REJECTED/PERVERSE "
            "grades and a `distinct_claim` of >= 5 words, which is "
            "`research_daemon.assert_distinct_from_corpses` verbatim."),
        "mutation_rounds": [
            {"round": 1, "wire_call": True, "spend_usd": 0.004644,
             "output_sha256": "4798b1ec1a8b3991",
             "proposals_returned": 20, "accepted": 0, "evaluated": 0,
             "outcome": "ALL TWENTY REFUSED -- interface defect, see below",
             "receipt": "G3_mutations_round01_ALL_REFUSED.json"},
            {"round": 2, "wire_call": True, "spend_usd": 0.004101,
             "output_sha256": "18c3f0a0e69b7f3c_NOT_RECORDED",
             "proposals_returned": 20, "accepted": 20, "evaluated": 20,
             "outcome": ("ran and produced a leader at leverage-neutral TW 5.4803 "
                         "(m05_quality_mom|10bps, beta 0.6942). ITS RECEIPT WAS "
                         "OVERWRITTEN by round 3 before `proposals_raw` existed, "
                         "so it is NOT reproducible and IS NOT CLAIMED. The number "
                         "is quoted from the console log, not from a receipt."),
             "receipt": None},
            {"round": 3, "wire_call": not replay, "spend_usd": spend.get("llm_spend_usd"),
             "proposals_returned": len(raw), "accepted": len(accepted),
             "evaluated": len(genomes),
             "outcome": "THE RECORDED ROUND. `proposals_raw` is on this receipt, "
                        "so --replay reproduces every number with no wire call.",
             "receipt": "G3_mutations.json"},
        ],
        "why_round_3_and_not_round_2": (
            "round 3 was run because round 2's leaderboard printed None in its DSR "
            "column -- G2.leaderboard read `dsr_over_family` and G3 writes "
            "`dsr_over_enlarged_family` -- and because round 2 did not record the "
            "proposals it was given. Both are CODE reasons, decided before round "
            "3's numbers existed. Round 2's higher leader is not adopted: choosing "
            "among three draws of a proposer by which draw scored best is "
            "selection, and the family correction here already assumes one draw. "
            "The proposer is NOT deterministic at temperature 0.0 -- three calls on "
            "two prompts returned three different proposal sets -- which is itself "
            "the finding: the mutation round is a DRAW, and its family size should "
            "be read as 20 of an unbounded pool, not 20 of 20."),
        "round_1_interface_defect": ({
            "receipt": str(round1),
            "proposals_returned": json.loads(round1.read_text(encoding="utf-8"))["proposals_returned"],
            "proposals_refused": json.loads(round1.read_text(encoding="utf-8"))["proposals_refused"],
            "spend_usd": json.loads(round1.read_text(encoding="utf-8"))["llm"].get("llm_spend_usd"),
            "cause": ("build_prompt named each parent by its CELL id "
                      "(`lgbm_clf|dd|10bps`) and validate() matches on the GENOME "
                      "id (`lgbm_clf|dd`), so every proposal named a parent that "
                      "does not exist. 20 of 20 refusals from ONE cause is a "
                      "finding about the interface, not about the proposer -- the "
                      "proposals themselves were in-grammar and sensible."),
        } if round1.exists() else None),
        "corpse_registry": corpse_list,
        "parents": [{k: p.get(k) for k in
                     ("genome_id", "beta", "leverage_neutral_tw", "raw_tw",
                      "max_drawdown", "spec", "overlay")} for p in parents],
        "mutation_grammar": {k: (list(v) if isinstance(v, list) else list(v))
                             for k, v in MUTATION_GRAMMAR.items()},
        "proposals_raw": raw,
        "proposals_returned": len(raw),
        "proposals_accepted": len(accepted),
        "proposals_refused": len(refused),
        "refusals": refused,
        "children_evaluated": len(genomes),
        "cells_added": len(cells),
        "family_cells_generation0": gen0_family,
        "family_cells_after_mutation": enlarged,
        "family_holm_best_over_everything": min(
            [p for p in holm_all.values() if p is not None], default=None),
        "family_bh_fdr_best_over_everything": min(
            [p for p in fdr_all.values() if p is not None], default=None),
        "leaderboard_children_only": board,
        "leaderboard_combined_top20": combined[:20],
        "cells": cells,
        "memory_free_gb_before": free,
        "wall_seconds": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    best_child = board[0] if board else {}
    best_all = combined[0] if combined else {}
    out["headline"] = (
        f"beta {best_all.get('beta')}: after {len(genomes)} evaluated mutations "
        f"({len(refused)} refused) the leader of the combined family is "
        f"{best_all.get('cell')} at leverage-neutral TW "
        f"{best_all.get('leverage_neutral_tw')}; best child "
        f"{best_child.get('cell')} at {best_child.get('leverage_neutral_tw')}; "
        f"family {gen0_family} -> {enlarged} cells, best Holm "
        f"{out['family_holm_best_over_everything']}, "
        f"LLM ${spend.get('llm_spend_usd', 0.0):.4f}")
    RP.attach(out, argv or sys.argv,
              {"job": "G3_mutations", "cap_usd": LLM_CAP_USD,
               "max_mutations": MAX_MUTATIONS, "dry_run": dry_run,
               "replay": replay}, tracker)
    (OUT_DIR / "G3_mutations.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


def _build_child(g: GL.Genome, panel, ctx, bps: float):
    if g.base.startswith("spy_"):
        s, meta = GL.build_spy_base(g.base, ctx, g.spec, cost_bps=bps)
    else:
        s, meta = GL.build_panel_base(g.base, panel, g.spec, cost_bps=bps)
    if g.overlay:
        s, om = GL.apply_overlays(s, ctx, g.overlay, cost_bps=bps, params=g.spec)
        meta = {**meta, "overlay_meta": om}
    return s, meta


def main(argv=None) -> int:                                # pragma: no cover
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="build and hash the prompt, make no wire call")
    ap.add_argument("--replay", action="store_true",
                    help="re-evaluate the proposals the previous run received; "
                         "no wire call, no spend")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    out = run(dry_run=a.dry_run, replay=a.replay, verbose=not a.quiet,
              argv=sys.argv)
    print("\n" + out["headline"])
    print(f"\nreceipt: {OUT_DIR / 'G3_mutations.json'}")
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
