"""PORTFOLIO FARM — thousands of virtual portfolios over one frozen history.

WHY THIS EXISTS (2026-08-24)
============================
Five months of guardrails and the demonstrated edge is 0%. The diagnosis in
`docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md` was that all ten arena books
select on ONE signal, so the arena tests portfolio TREATMENT and never alpha
SOURCE. The second diagnosis, from Murat's review the same day, is worse: the
arena can only learn at the rate the calendar advances — one strategy, one day
at a time.

This package answers both with the same object. A **policy** is a small frozen
record (signal, holding period, breadth, sizing, universe, costs). Hundreds of
them run over the same replayed history in minutes, paying real costs, and the
leaderboard is terminal wealth — not a p-value.

THE FOUR THINGS THAT DO NOT RELAX (`CLAUDE.md`, three licences)
---------------------------------------------------------------
Exploration here is `PRODUCT_EXPERIMENT`: post-hoc is allowed, many variants are
allowed, a failed variant is a FAILED_VARIANT and not a closed mechanism. What
is never allowed, and is enforced in code rather than by intention:

  1. **No information before it was public.** Signals are computed from a panel
     slice truncated at the decision date; `replay.py` hands the signal function
     a view that physically cannot reach forward. `test_portfolio_farm_pit.py`
     plants perfect foresight in the panel and asserts the engine cannot find
     it.
  2. **No target leakage.** The label is the realised forward NAV, produced by
     the simulator, never an input.
  3. **Costs are not optional.** `Policy` refuses to construct with zero costs
     unless `zero_cost_diagnostic=True` is declared, and every result carries
     that flag so a frictionless number can never be quoted as a net one.
  4. **A candidate that enters forward paper is frozen.** `policy_id` is the
     hash of the whole record; a changed parameter is a different policy, never
     an edit.

WHAT IT IS NOT
--------------
Not a claim engine. Nothing here may be cited as alpha (`RESEARCH_CLAIM` needs
preregistration, MDE, multiplicity control, holdout). A farm winner is a
CANDIDATE for a frozen forward book — the next tier — and that is all.
"""

from backend.services.portfolio_farm.policy import Policy, grid  # noqa: F401
