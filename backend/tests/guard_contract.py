"""Every guard ships with a test that feeds it a MISSING input and asserts a refusal.

WHY THIS IS A SHARED TEMPLATE AND NOT A HABIT
=============================================
The failure has now recurred often enough to deserve a mechanical answer rather
than more discipline:

* `n_effective = n` made five false kills in a test and, mirrored, false PASSES
  in a power gate (S41, then its mirror).
* The lift audit printed a CLEAN VERDICT over 400 of 424 unscoreable rows —
  inside the tool built to prevent exactly that class.
* The lift audit then reported "no base rate recorded" for the one number it
  had been ordered to check, because the value lived under a key it did not
  look up.
* `iif1_read_gate.check_read` still takes `n_graded_nights` as an INPUT.

Every one of these is the same shape: a guard handed nothing, and answering
anyway. The canon rule is "a guard must DERIVE what it checks from data it can
see, or refuse" — and the way that rule stops being honour-system is a test
that hands each guard nothing and demands the refusal.

WHY ENROLMENT IS DERIVED RATHER THAN LISTED
===========================================
A registry somebody has to remember to add to is the honour system with extra
steps. `discover_guard_modules` finds guards the way the codebase actually
marks them — a module defining its own refusal exception — so a NEW guard is
enrolled by existing, and the contract test fails until it is covered.
"""

from __future__ import annotations

import ast
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[1] / "services"

#: WHY THE NAME SUFFIX WAS NOT ENOUGH, AND THE RULE IS NOW THE BASE CLASS.
#:
#: The first version of this file looked for `*Refusal` / `*Refused` /
#: `NotReportable` / `IsNotEvidence`, on the theory that the codebase spells
#: refusals consistently. It does not. `copy_lab/store` raises **ConfigDrift**
#: when a lane was never seeded — a textbook missing-input refusal — and the
#: suffix rule walked straight past it. A discovery rule that under-detects
#: makes the enrolment check PASS while missing guards, which is the same
#: failure it was written to stop, one level up.
#:
#: So discovery is now the structural fact rather than the naming convention:
#: a module that defines its own exception type has a refusal path, and every
#: refusal path is either contract-tested or classified with a reason.
EXCEPTION_BASES = {"RuntimeError", "Exception", "ValueError", "LookupError",
                   "AssertionError", "KeyError", "TypeError"}

#: Modules whose custom exception is an OPERATIONAL failure — the network was
#: down, the budget ran out, the provider returned nothing — rather than a
#: guard refusing an inference. These do not need a missing-input contract, and
#: each says why in one line so that "exempt" costs a sentence instead of
#: nothing. A new module lands in neither table and fails the enrolment test.
NOT_INPUT_GUARDS: dict[str, str] = {
    "data_fetcher": "RateLimited — upstream throttling, not an inference",
    "data_integrity": "raised on data that arrived wrong, not on data absent",
    "base": "ProviderUnavailable/ProviderError — transport failures",
    "pm_catalysts": "CatalystFetchError — fetch failure",
    "prediction_markets": ("PredictionMarketFetchError — fetch failure, "
                           "raised BEFORE any write; the no-write contract "
                           "is exercised directly in "
                           "test_prediction_markets.py"),
    "why_moved": "PricingError — a price lookup failed",
    "llm_research": "LLMUnavailable/BudgetExhausted — service and spend",
    "autopsy_llm": "AutopsyReplyUnusable — a model returned unparseable text",
    "investigator_tools": "BudgetExhausted — spend ceiling, enforced elsewhere",
    "research_budget": "ResearchBudgetExhausted — spend ceiling",
    "market_sessions": "SessionCalendarUnavailable — missing calendar file",
    "opportunity_funnel": "FunnelError — pipeline plumbing",
    "pm_engine": "BookError — book arithmetic",
    "pm_reconcile": "ReconcileError — reconciliation mismatch",
    "shadow_portfolios": "ShadowError — book plumbing",
    "recommendation": "RankLeadershipError — ranking plumbing",
    "lanes": "LaneConfigError — malformed config, a type error not a guard",
    "execution": "NotExecutable — an order could not be placed",
    "events": "TeacherEventInvalid — schema validation",
    "signal_registry": "ClosedSignalError/RegistryError — registry lookups",
    "iif1_prereg": ("FrozenPreregMissing/Drifted — covered by the IIF-1 "
                    "preflight suite, which asserts both refusals directly"),
    "panel": ("PanelUnavailable (portfolio_farm) — a CRSP year the replay "
              "window needs is not on disk. Refuses rather than silently "
              "replaying a shorter history, which would report a CAGR over a "
              "period nobody declared. Asserted directly in "
              "test_portfolio_farm_replay.py"),
    "characteristics": (
        "CharacteristicUnavailable (portfolio_farm) — the finratio parquets a "
        "non-price signal needs are absent, or a caller named a characteristic "
        "neither era file carries. Both are REFUSALS by design: an all-NaN "
        "column would put a policy on the leaderboard as a signal that does "
        "not work. It takes no user input and guards no request field, so it "
        "is not a missing-input guard; the refusals are exercised in "
        "test_portfolio_farm_characteristics.py"),
    "revisions": (
        "RevisionsUnavailable (portfolio_farm) — the IBES consensus parquets "
        "the analyst-state signals need are absent, or a caller named a "
        "revision series this module does not serve. Same shape and same "
        "reasoning as `characteristics` above: both are REFUSALS by design, "
        "because a run that silently dropped its only BEHAVIOURAL signal would "
        "read as a result ABOUT that signal. It takes no user input and guards "
        "no request field, so it is not a missing-input guard; the refusals "
        "are exercised in test_portfolio_farm_revisions.py"),
    "policy": ("PolicyError (portfolio_farm) — a policy asks for a signal or "
               "sizing the engine does not implement, or zero costs without "
               "declaring the frictionless diagnostic. Every branch is "
               "exercised in test_portfolio_farm_policy.py; the missing-input "
               "shape does not apply, because a Policy has no inputs to be "
               "missing — it IS the declaration"),
    "deepseek_balance": ("BalanceUnavailable — the PROVIDER could not be "
                         "asked (no key, transport failure, or a payload with "
                         "no USD row). Not a missing-input inference: this "
                         "module infers nothing, it reports one number the "
                         "vendor owns. The contract that matters here is the "
                         "opposite one — that a failed read never degrades to "
                         "0.0, which would read as 'the night was free' — and "
                         "test_deepseek_balance.py asserts that directly"),
    "investigator_night": ("DecisionTimeStale/NightWouldSpanTheOpen/"
                           "SandboxRequired — covered by the night preflight "
                           "tests, which exercise each refusal on the real "
                           "path rather than a synthetic missing input"),
}


def discover_guard_modules() -> dict[str, list[str]]:
    """Modules under services/ that define their own exception type.

    Parses rather than imports: a module that refuses at import time (several
    do, when their data is absent) must still be discoverable.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(SERVICES.rglob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        names = [n.name for n in ast.walk(tree)
                 if isinstance(n, ast.ClassDef)
                 and any(isinstance(b, ast.Name) and b.id in EXCEPTION_BASES
                         for b in n.bases)]
        if names:
            found[path.stem] = names
    return found


def assert_refuses_missing_input(call, *, exc, what: str) -> None:
    """`call` must RAISE `exc` when handed a missing/undeclared input.

    Not "must return None", not "must warn". A guard that degrades quietly is
    the same guard that emitted a clean verdict over 400 unscoreable rows: the
    caller reads a result and cannot tell it was computed from nothing.
    """
    try:
        result = call()
    except exc:
        return
    except Exception as e:                                       # noqa: BLE001
        raise AssertionError(
            f"{what}: refused with {type(e).__name__} rather than "
            f"{exc.__name__}. A refusal the caller cannot catch by type is a "
            f"crash, and crashes get wrapped in try/except.") from e
    raise AssertionError(
        f"{what}: returned {result!r} instead of refusing. This is the "
        f"failure that recurs — answering an input that was never supplied.")
