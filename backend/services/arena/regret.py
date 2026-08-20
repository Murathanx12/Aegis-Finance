"""The regret reader: what did passing cost?

Studying losers as hard as winners (CLAUDE.md rule 4) needs the thing a P&L
curve structurally cannot show — the names the book looked at, ranked, and
did NOT buy. The arena writes those as REJECT experiences carrying the same
`information_state_hash` as the chosen legs from the same decision, so the
counterfactual is a JOIN, not a reconstruction.

This is a READER. The ledger deliberately stores no joined regret number
(`experience.py` docstring): regret has more than one honest definition and
freezing one into an append-only file would make the others unavailable
forever. Two are computed here, side by side:

  vs_named_alternative   the specific name the REJECT row points at
                         (`chosen_alternative`). NOTE: the engine currently
                         writes the TOP pick there for every reject, which
                         makes this the "vs the best thing we did instead"
                         reading — not "vs the marginal name it displaced".
  vs_chosen_basket       the equal-weighted mean excess of everything the book
                         DID choose from the same information state. This is
                         the reading that answers "would swapping have helped",
                         and it is the one to prefer while the field above is
                         a constant.

Positive regret = the pass cost the book something. Unmatched legs are
REPORTED, never dropped: a regret statistic computed only over the rejects
that happened to resolve is a survivorship statistic.
"""

from __future__ import annotations

from backend.services.arena import experience as exp_mod
from backend.services.arena import store

LEGS = exp_mod.LEGS if hasattr(exp_mod, "LEGS") else {}

CHOSEN_ACTIONS = frozenset({"ENTER", "HOLD", "SWAP_IN"})
PASS_ACTIONS = frozenset({"REJECT"})

_LEG_KEYS = {
    "forecast": "excess_return",
    "execution": "execution_excess_return",
}


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def pairs(*, root=None, leg: str = "forecast") -> dict:
    """Every resolvable (rejected, chosen) pair, per horizon.

    Returns rows plus the counts of what could NOT be paired and why — the
    denominators that make the mean interpretable.
    """
    if leg not in _LEG_KEYS:
        raise ValueError(f"unknown leg {leg!r}; expected {sorted(_LEG_KEYS)}")
    key = _LEG_KEYS[leg]

    exps = store.read_experiences(root)
    outs = [o for o in store.read_outcomes(root)
            if int(o.get("schema_version") or 1) >= exp_mod.OUTCOME_SCHEMA_VERSION]
    # (experience_id, horizon) -> excess on the requested leg
    excess = {(o["experience_id"], o["horizon_days"]): o.get(key)
              for o in outs}
    horizons = sorted({o["horizon_days"] for o in outs})

    groups: dict[tuple[str, str], list[dict]] = {}
    for e in exps:
        groups.setdefault((e.get("book_id"), e.get("information_state_hash")),
                          []).append(e)

    rows: list[dict] = []
    skipped = {"no_chosen_leg_in_group": 0, "reject_unresolved": 0,
               "basket_unresolved": 0, "named_alternative_unresolved": 0,
               "named_alternative_absent": 0}
    for (book_id, is_hash), members in sorted(groups.items(),
                                              key=lambda kv: str(kv[0])):
        chosen = [m for m in members if m.get("action") in CHOSEN_ACTIONS]
        rejects = [m for m in members if m.get("action") in PASS_ACTIONS]
        if not rejects:
            continue
        if not chosen:
            skipped["no_chosen_leg_in_group"] += len(rejects)
            continue
        by_ticker = {m["entity_key"]: m for m in chosen}
        for h in horizons:
            basket = [excess[(m["experience_id"], h)] for m in chosen
                      if excess.get((m["experience_id"], h)) is not None]
            basket_mean = _mean(basket)
            for r in rejects:
                r_ex = excess.get((r["experience_id"], h))
                if r_ex is None:
                    skipped["reject_unresolved"] += 1
                    continue
                alt_t = r.get("chosen_alternative")
                alt = by_ticker.get(alt_t) if alt_t else None
                alt_ex = (excess.get((alt["experience_id"], h))
                          if alt is not None else None)
                if alt_t and alt is None:
                    skipped["named_alternative_absent"] += 1
                elif alt is not None and alt_ex is None:
                    skipped["named_alternative_unresolved"] += 1
                if basket_mean is None:
                    skipped["basket_unresolved"] += 1
                rows.append({
                    "book_id": book_id,
                    "information_state_hash": is_hash,
                    "decision_date": r.get("ts"),
                    "horizon_days": h,
                    "rejected": r["entity_key"],
                    "rejected_rank": r.get("rank"),
                    "rejected_excess": r_ex,
                    "named_alternative": alt_t,
                    "named_alternative_excess": alt_ex,
                    "chosen_basket_n": len(basket),
                    "chosen_basket_excess": basket_mean,
                    "regret_vs_named": (r_ex - alt_ex
                                        if alt_ex is not None else None),
                    "regret_vs_basket": (r_ex - basket_mean
                                         if basket_mean is not None else None),
                })
    return {"leg": leg, "key": key, "n_pairs": len(rows),
            "horizons": horizons, "unpaired": skipped, "rows": rows}


def summary(*, root=None, leg: str = "forecast", min_n: int = 20,
            worst_k: int = 10) -> dict:
    """Aggregated regret per (book, horizon), with the same thin-cell refusal
    the reliability ledger uses — a mean regret over three passes is three
    passes."""
    p = pairs(root=root, leg=leg)
    cells: dict[str, list[dict]] = {}
    for r in p["rows"]:
        cells.setdefault(f"{r['book_id']}|h{r['horizon_days']}", []).append(r)
    out = {}
    for k, rs in sorted(cells.items()):
        vs_basket = [r["regret_vs_basket"] for r in rs
                     if r["regret_vs_basket"] is not None]
        vs_named = [r["regret_vs_named"] for r in rs
                    if r["regret_vs_named"] is not None]
        head = {"n": len(rs), "n_vs_basket": len(vs_basket),
                "n_vs_named": len(vs_named), "min_n": min_n}
        if len(vs_basket) < min_n:
            out[k] = {**head, "verdict": "REFUSED_THIN",
                      "note": (f"n={len(vs_basket)} paired regrets < "
                               f"min_n={min_n}; no mean computed")}
            continue
        costly = sum(1 for x in vs_basket if x > 0)
        out[k] = {
            **head, "verdict": "REPORTED",
            "mean_regret_vs_basket": round(_mean(vs_basket), 6),
            "mean_regret_vs_named": (round(_mean(vs_named), 6)
                                     if vs_named else None),
            "share_passes_that_cost": round(costly / len(vs_basket), 4),
        }
    worst = sorted((r for r in p["rows"]
                    if r["regret_vs_basket"] is not None),
                   key=lambda r: -r["regret_vs_basket"])[:worst_k]
    return {"leg": leg, "basis": (exp_mod.FORECAST_BASIS if leg == "forecast"
                                  else exp_mod.EXECUTION_BASIS),
            "n_pairs": p["n_pairs"], "unpaired": p["unpaired"],
            "cells": out, "worst_passes": worst,
            "validation_status": "PRODUCT_EXPERIMENT", "simulation": True}
