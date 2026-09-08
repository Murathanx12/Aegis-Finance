"""INVARIANT 17 -- the four-stage information chain, on every receipt.

    prediction -> selection -> construction -> holding/exit

Five months were spent on stage one and stage one is not where the money died:
the last two stages were measured to destroy most of what the first produced
(transfer coefficient 0.13 -> 0.49 by construction alone; turnover 0.90 -> 0.53
by holding alone). A receipt that reports only stage one cannot say where the
information went, so from this block on every receipt reports all four.

WHAT IS NEW HERE AND WHAT IS NOT
================================
Stages 1-3 are `learner.fundamental_law` -- IC, effective breadth and the
Clarke-de Silva-Thorley transfer coefficient already exist and are already
tested, and re-deriving them here would create a second number for the same
quantity. This module WRAPS that receipt and adds the two things it does not
have:

* **stage 4**: hold statistics and exit attribution by TYPED reason;
* **the defect flag**: TC < 0.5 marks the book a CONSTRUCTION DEFECT and its
  signal verdict UNREADABLE.

WHY "UNREADABLE" AND NOT "FAILED"
=================================
A book whose construction transfers less than half of its signal has not
tested its signal. Reporting "the signal does not work" from such a book is
the mistake the invariant exists to stop -- it closes a mechanism on evidence
about a portfolio. So the verdict word is UNREADABLE_CONSTRUCTION_DEFECT, and
the book's own wealth numbers stay exactly as computed beside it: the book is
still a book, it is only not evidence about its signal.

WHY A MISSING TC IS NOT A PASSING TC
====================================
`transfer_coefficient` returns None when it cannot be measured (a constant
signal, too few admissible names). None is reported as CANNOT_DETERMINE and is
NOT treated as >= 0.5. A check that did not run is not a check that passed.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

#: Below this, the construction is a defect and the signal verdict is
#: unreadable from the book (roadmap amendment invariant 17).
TC_DEFECT_FLOOR = 0.5

CANNOT_DETERMINE = "CANNOT DETERMINE"


def hold_statistics(holdings_by_period: Mapping[Any, Sequence[Any]]) -> dict:
    """Stage four, part one: how long anything actually stayed.

    `holdings_by_period` is `{period_label: [identifier, ...]}` in period order.
    Turnover is the one-sided name turnover between consecutive periods --
    `|entered| / |held now|` -- which is the definition the construction-tax
    work used, so the numbers here are comparable with it.
    """
    periods = list(holdings_by_period)
    if not periods:
        return {"verdict": f"{CANNOT_DETERMINE} (no periods)"}
    try:
        periods = sorted(periods, key=str)
    except TypeError:                                     # pragma: no cover
        pass
    sets = [set(holdings_by_period[p]) for p in periods]

    spells: Counter = Counter()          # identifier -> consecutive periods held
    completed: list[int] = []
    running: dict[Any, int] = {}
    turnovers: list[float] = []
    for i, held in enumerate(sets):
        if i:
            prev = sets[i - 1]
            entered = held - prev
            turnovers.append(len(entered) / len(held) if held else 0.0)
            for gone in prev - held:
                completed.append(running.pop(gone, 1))
        for name in held:
            running[name] = running.get(name, 0) + 1
        spells.update(held)
    open_spells = list(running.values())
    all_spells = completed + open_spells

    return {
        "n_periods": len(periods),
        "first_period": str(periods[0]),
        "last_period": str(periods[-1]),
        "mean_names_per_period": float(np.mean([len(s) for s in sets])),
        "mean_hold_periods": float(np.mean(all_spells)) if all_spells else None,
        "median_hold_periods": float(np.median(all_spells)) if all_spells else None,
        "max_hold_periods": int(max(all_spells)) if all_spells else None,
        "n_completed_spells": len(completed),
        "n_open_spells": len(open_spells),
        "mean_turnover_one_sided": float(np.mean(turnovers)) if turnovers else None,
        "note": ("turnover is |entered| / |held| between consecutive periods, "
                 "one-sided; open spells are counted at their length so far and "
                 "are reported separately because they are censored, not short"),
    }


def exit_attribution(exits: Sequence[Mapping[str, Any]], *,
                     declared_priority: Sequence[str] = ()) -> dict:
    """Stage four, part two: WHY each position left, by typed reason.

    Each entry is `{"reason": <typed reason>, "pnl": <float, optional>}`.
    An exit with no reason is counted as `UNTYPED` and is a finding, never
    dropped: an untyped exit is the one that cannot be attributed, which is
    exactly the one worth counting.
    """
    if not exits:
        return {"verdict": f"{CANNOT_DETERMINE} (no exits recorded)",
                "n_exits": 0}
    counts: Counter = Counter()
    pnl: dict[str, list[float]] = {}
    for e in exits:
        reason = str(e.get("reason") or "UNTYPED")
        counts[reason] += 1
        v = e.get("pnl")
        if v is not None and np.isfinite(float(v)):
            pnl.setdefault(reason, []).append(float(v))
    n = sum(counts.values())
    by_reason = {
        r: {"n": int(c), "share": c / n,
            "mean_pnl": (float(np.mean(pnl[r])) if pnl.get(r) else None),
            "win_rate": (float(np.mean([x > 0 for x in pnl[r]])) if pnl.get(r) else None)}
        for r, c in sorted(counts.items(), key=lambda kv: -kv[1])
    }
    undeclared = sorted(r for r in counts
                        if declared_priority and r not in declared_priority
                        and r != "UNTYPED")
    return {
        "n_exits": int(n),
        "by_reason": by_reason,
        "n_untyped": int(counts.get("UNTYPED", 0)),
        "reasons_not_in_declared_priority": undeclared,
        "declared_priority": list(declared_priority),
        "note": ("an exit with no reason is counted as UNTYPED rather than "
                 "dropped; a reason absent from the declared priority means the "
                 "book exited for something its contract never named"),
    }


def information_chain(*, panel: pd.DataFrame | None = None,
                      pred_col: str | None = None,
                      weights_by_period: Mapping[Any, Mapping[Any, float]] | None = None,
                      net: pd.Series | None = None,
                      benchmark: pd.Series | None = None,
                      beta: float | None = None,
                      exits: Sequence[Mapping[str, Any]] = (),
                      declared_exit_priority: Sequence[str] = (),
                      ret_col: str = "fwd_1m",
                      period_col: str = "month",
                      id_col: str = "permno",
                      periods_per_year: int = 12) -> dict:
    """All four stages, or an explicit CANNOT_DETERMINE per stage.

    Every argument is optional because a book can be expressed through the
    `Strategy` contract before its panel is available, and a chain block that
    invented zeros for the stages it could not see would be worse than one that
    names them: "the construction expresses nothing" is a finding, "not
    measured" is not.
    """
    stages: dict[str, Any] = {}
    law: dict[str, Any] | None = None

    if panel is not None and pred_col and weights_by_period is not None:
        from learner import fundamental_law as FL
        law = FL.receipt(panel, pred_col, weights_by_period,
                         net=net, benchmark=benchmark, beta=beta,
                         ret_col=ret_col, month_col=period_col, id_col=id_col,
                         periods_per_year=periods_per_year)
        stages["1_prediction"] = law.get("information_coefficient")
        stages["2_selection"] = law.get("effective_breadth")
        stages["3_construction"] = law.get("transfer_coefficient")
    else:
        missing = [n for n, v in (("panel", panel), ("pred_col", pred_col),
                                  ("weights_by_period", weights_by_period))
                   if v is None or v == ""]
        why = f"{CANNOT_DETERMINE} (not supplied: {', '.join(missing)})"
        stages["1_prediction"] = {"verdict": why}
        stages["2_selection"] = {"verdict": why}
        stages["3_construction"] = {"verdict": why}

    holdings = ({p: list(w) for p, w in weights_by_period.items()}
                if weights_by_period else {})
    stages["4_holding_exit"] = {
        "hold_statistics": (hold_statistics(holdings) if holdings else
                            {"verdict": f"{CANNOT_DETERMINE} (no holdings supplied)"}),
        "exit_attribution": exit_attribution(exits,
                                             declared_priority=declared_exit_priority),
    }

    tc = None
    if isinstance(stages.get("3_construction"), dict):
        tc = stages["3_construction"].get("tc")
    defect = bool(tc is not None and float(tc) < TC_DEFECT_FLOOR)
    if tc is None:
        readable = f"{CANNOT_DETERMINE} (TC not measured; a check that did not run "
        readable += "is not a check that passed)"
    elif defect:
        readable = "UNREADABLE_CONSTRUCTION_DEFECT"
    else:
        readable = "READABLE"

    return {
        "invariant": ("17 -- a book receipt reports where information died: IC, "
                      "effective breadth, transfer coefficient, hold statistics "
                      "and exit attribution by typed reason"),
        "identity": (law or {}).get(
            "identity", "IR ~= IC x sqrt(BR) x TC  (Grinold-Kahn; TC after "
                        "Clarke-de Silva-Thorley)"),
        "stages": stages,
        "transfer_coefficient": tc,
        "tc_defect_floor": TC_DEFECT_FLOOR,
        "construction_defect": defect,
        "signal_verdict_readable_from_this_book": readable,
        "reading": ("a book with TC below the floor has not tested its signal. "
                    "Its wealth numbers stand exactly as computed; what does not "
                    "stand is any sentence of the form 'the signal does not "
                    "work', which would close a mechanism on evidence about a "
                    "portfolio."),
        "fundamental_law": law,
    }
