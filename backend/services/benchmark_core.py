"""PC-PAPER benchmark core (CHUNK C20, owner decision D14). PURE; never an order.

The C2 reviewer's lever (docs/reviews/REVIEW_2026-10-06_C2_PC_MANDATE_AND_SIM_OWNER.md):
the day's decision contract already resolves ~99.75% of capital to a
"benchmark core", while the broker holds ~80% CASH. `decision_contract.
positions_reconciliation` therefore prints POSITIONS_DISAGREE every day. The
lever is to make the account hold what the contract claims: `1 - active_gross`
in the benchmark, and to grade every active sleeve as EXCESS over that core.

What this module does and does not do:

* `core_plan` computes the core's WANTED weight from the acting sleeve weights
  (after the order-path gate) and what `pc_broker.plan_orders` will DELIVER
  under its unchanged `MAX_NAME_FRAC`. With today's limits the flag alone holds
  at most 12% in SPY, and the line says CORE_CLIPPED_BY_MAX_NAME_FRAC. A full
  core needs a separate owner decision about that limit; nothing here loosens it.
* `worst_case` prints session protocol item 4 for core + sleeves, in dollars:
  the core moves with SPY, so a k-sigma SPY day on the core is its own line,
  beside the sleeves' k-sigma loss, the panel's worst SPY day, and
  sum|notional| / equity.
* `sleeve_excess` / `account_attribution` are the grading convention: a
  sleeve name is graded `r_name - r_core`; the account's sleeve contribution is
  `r_account - w_core * r_core` (cash earns 0 here; stated, not hidden).

The flag is `config.PC_BENCHMARK_CORE` (default False). Flag OFF: `core_plan`
returns `enabled=False` and the caller changes nothing.
"""

from __future__ import annotations

from typing import Optional

from backend import config as _cfg

CORE_STATE = "CORE"


def core_plan(acting_weights: dict[str, float], *, enabled: bool,
              symbol: Optional[str] = None,
              max_name_frac: Optional[float] = None) -> dict:
    """The core target for one plan cycle.

    `acting_weights` are the sleeve weights that will actually be held (PROBE /
    EXPLOIT names whose sleeve is acting), AFTER the order-path gate. The core
    wants `1 - sum(acting)`; `pc_broker.plan_orders` clips any single target at
    `max_name_frac`, so `deliver_weight` is what the account will hold."""
    from backend.services import pc_broker as PB                   # noqa: PLC0415
    sym = str(symbol or _cfg.PC_BENCHMARK_CORE_SYMBOL).upper()
    cap = float(PB.MAX_NAME_FRAC if max_name_frac is None else max_name_frac)
    if not enabled:
        return {"enabled": False, "applied": False, "symbol": sym,
                "line": "benchmark core: OFF (config.PC_BENCHMARK_CORE=False)"}
    if sym in {str(s).upper() for s in acting_weights}:
        return {"enabled": True, "applied": False, "symbol": sym,
                "refused": f"{sym} is already a sleeve name this cycle",
                "line": f"benchmark core: REFUSED -- {sym} is already a sleeve name"}
    active = sum(max(0.0, float(w)) for w in acting_weights.values())
    want = max(0.0, 1.0 - active)
    deliver = min(want, cap)
    clipped = deliver < want - 1e-12
    bench = str(getattr(_cfg, "DECISION_BENCHMARK_SYMBOL", "SPY")).upper()
    grading = {
        "basis": "excess_over_core",
        "core_symbol": sym,
        "decision_benchmark": bench,
        "consistent": bench == sym,
        "rule": (f"each sleeve name is graded r_name - r_{sym} over its own window "
                 f"(decision_ledger already grades vs {bench}); the account's sleeve "
                 f"contribution = r_account - w_core x r_{sym}; cash earns 0 in this "
                 f"attribution"),
    }
    line = (f"benchmark core: ON -- active {active:.2%}, core wants {want:.2%} {sym}, "
            f"delivers {deliver:.2%}"
            + (f" (CORE_CLIPPED_BY_MAX_NAME_FRAC {cap:.0%}: the remaining "
               f"{want - deliver:.2%} stays cash; a full core is a separate owner "
               f"decision about that limit)" if clipped else "")
            + f"; grading: excess over {sym}")
    return {"enabled": True, "applied": want > 0, "symbol": sym,
            "active_gross": active, "want_weight": want, "deliver_weight": deliver,
            "clipped": clipped, "max_name_frac": cap, "grading": grading,
            "status": "CORE_CLIPPED_BY_MAX_NAME_FRAC" if clipped else "CORE_FULL",
            "line": line}


def worst_case(*, equity: float, core_frac: float, core_sigma: float,
               sleeve_weights: dict[str, float], sleeve_sigmas: dict[str, float],
               fallback_sigma: float, k: Optional[float] = None,
               core_worst_day: Optional[float] = None, label: str = "") -> dict:
    """Session protocol item 4 for core + sleeves, in dollars (rho = 1).

    No stop is declared on PC-PAPER, so the ceiling is the whole gross."""
    kk = float(_cfg.PROBE_WORST_CASE_SIGMA if k is None else k)
    eq = float(equity)
    core_loss = float(core_frac) * kk * float(core_sigma) * eq
    sl = 0.0
    for s, w in sleeve_weights.items():
        sig = float(sleeve_sigmas.get(s) or fallback_sigma)
        sl += max(0.0, float(w)) * kk * sig * eq
    sleeve_gross = sum(max(0.0, float(w)) for w in sleeve_weights.values())
    gross = float(core_frac) + sleeve_gross
    out = {"label": label, "equity_usd": eq, "k_sigma": kk,
           "core_frac": float(core_frac), "core_daily_sigma": float(core_sigma),
           "sleeve_gross": sleeve_gross, "gross_over_equity": gross,
           "core_k_sigma_usd": -core_loss, "sleeves_k_sigma_usd": -sl,
           "total_k_sigma_usd": -(core_loss + sl),
           "total_k_sigma_frac": -(core_loss + sl) / eq if eq else None,
           "no_stop_ceiling_usd": -gross * eq,
           "limit_frac": float(_cfg.PC_WORST_CASE_MAX_FRAC_OF_EQUITY)}
    if core_worst_day is not None:
        out["core_worst_day_return"] = float(core_worst_day)
        out["core_worst_day_usd"] = float(core_frac) * float(core_worst_day) * eq
    out["passes_limit"] = (core_loss + sl) <= out["limit_frac"] * eq + 1e-9
    out["line"] = (f"{label}: core {core_frac:.0%} x {kk:g} x {core_sigma:.2%} = "
                   f"-${core_loss:,.0f}; sleeves {sleeve_gross:.0%} gross = -${sl:,.0f}; "
                   f"total -${core_loss + sl:,.0f} ({(core_loss + sl) / eq:.2%} of "
                   f"${eq:,.0f}, limit {out['limit_frac']:.0%}); "
                   f"sum|notional|/equity {gross:.2f}"
                   + (f"; the panel's worst {_cfg.PC_BENCHMARK_CORE_SYMBOL} day "
                      f"({core_worst_day:.2%}) on the core = -${abs(out['core_worst_day_usd']):,.0f}"
                      if core_worst_day is not None else ""))
    return out


def sleeve_excess(name_returns: dict[str, float], core_return: float) -> dict[str, float]:
    """Each sleeve name's return in excess of the core over the same window."""
    return {s: float(r) - float(core_return) for s, r in name_returns.items()}


def account_attribution(account_return: float, core_return: float,
                        core_weight: float) -> dict:
    """Split an account return into the core's part and the sleeves' part.

    `sleeves = r_account - w_core x r_core` (cash earns 0 here). The excess
    over a 100% core account is `r_account - r_core`."""
    core_part = float(core_weight) * float(core_return)
    return {"core_part": core_part,
            "sleeves_part": float(account_return) - core_part,
            "excess_over_full_core": float(account_return) - float(core_return)}
