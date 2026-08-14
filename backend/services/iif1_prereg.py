"""The frozen INTERNET-INVESTIGATOR-FWD-1 pre-registration, and the check that
the runtime still matches it.

WHY THIS LIVES IN `services/` AND NOT ONLY IN `tests/`
======================================================
The first version of this check was a test, and it did this when the
`Aegis module` sibling tree was absent:

    if not cfg.exists():
        pytest.skip("Aegis module not present in this checkout")

A skip is green, so on every CI container — which clones one repo — the single
assertion standing between "the trial ran the registered rule" and "the trial
ran some other rule" reported success while executing nothing.

Making that a hard test failure turned CI red, which is the check working: CI
genuinely has no sibling tree. But it also pointed at the real mistake, which
was placing the guard in the one context that never spends money.

**CI does not accrue. The nightly runner does.** So the enforcement lives here,
and `run_night` calls it before constructing a real vendor call. A context that
cannot accrue may declare itself exempt; a night that is about to spend cannot.
The exemption is deliberately not readable by `verify_or_refuse` for that
reason.

THE SURFACE THAT IS CHECKED
===========================
Not just the trigger rule. `ARMS` — the thing the entire trial compares — plus
the requested model, the benchmark and both ceilings are all retyped into the
runner, and drift in any of them means the accrual ran a different trial than
the one on the registry.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import types

#: Declared by a context that legitimately has no `Aegis module` sibling and
#: performs NO accrual — CI, a frontend build, a prod image. It exempts the
#: test-time consistency assertion. It does NOT exempt `verify_or_refuse`.
OPT_OUT_ENV = "AEGIS_IIF1_PREREG_ABSENT_OK"

CONFIG_PATH = (pathlib.Path(__file__).resolve().parents[2] / ".."
               / "Aegis module" / "scripts" / "iif1_config.py").resolve()


class FrozenPreregMissing(RuntimeError):
    """The frozen pre-registration could not be read. Never a skip."""


class FrozenPreregDrifted(RuntimeError):
    """The runtime disagrees with the registered rule. Never a warning."""


def load_frozen_config(*, allow_opt_out: bool = True) -> types.ModuleType | None:
    """The frozen config module.

    Returns `None` only when the config is absent AND `OPT_OUT_ENV` is exactly
    `"1"` AND `allow_opt_out` is set. Otherwise raises. A missing sibling tree
    and a correct sibling tree must not both report green.
    """
    if CONFIG_PATH.exists():
        spec = importlib.util.spec_from_file_location("iif1_config",
                                                      CONFIG_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)                            # type: ignore
        return mod

    if allow_opt_out and os.environ.get(OPT_OUT_ENV) == "1":
        print(f"\n*** {OPT_OUT_ENV}=1 — the IIF-1 frozen-config consistency "
              f"check DID NOT RUN in this checkout. The runtime trigger rule, "
              f"arms, observables and budget ceilings are UNVERIFIED against "
              f"the pre-registration. This is acceptable ONLY where no accrual "
              f"happens; `verify_or_refuse` ignores this variable.\n")
        return None

    raise FrozenPreregMissing(
        f"the frozen IIF-1 pre-registration config is missing at "
        f"{CONFIG_PATH}.\n\n"
        f"This check is what guarantees the trial runs the rule that was "
        f"registered. It will not downgrade itself to a skip.\n\n"
        f"Either check out the `Aegis module` sibling repo, or — if this "
        f"context genuinely never accrues — set {OPT_OUT_ENV}=1 to declare "
        f"that explicitly.")


def runtime_surface() -> dict:
    """Every frozen value the runtime carries its own copy of."""
    from backend.services import investigator_agent as A
    from backend.services import investigator_night as N
    from backend.services import investigator_triggers as TR
    return {
        "TRIGGER_WEIGHTS": dict(TR.TRIGGER_WEIGHTS),
        "TRIGGERS_PER_NIGHT": TR.TRIGGERS_PER_NIGHT,
        "MIN_PRICE": TR.MIN_PRICE,
        "MIN_DOLLAR_VOLUME_20D": TR.MIN_DOLLAR_VOLUME_20D,
        "ARMS": tuple(N.ARMS),
        "REQUEST_MODEL": N.REQUEST_MODEL,
        "BENCHMARK": N.BENCHMARK,
        "NIGHTLY_MAX_USD": N.NIGHTLY_MAX_USD,
        "NIGHTLY_MAX_CALLS": N.NIGHTLY_MAX_CALLS,
        # Added 2026-08-15. `MAX_TOKENS` was the constant that voided Night 1,
        # and it earned a place here by being able to bias the primary contrast
        # while appearing in no registered document — the same class of hole as
        # a caller-overridable "frozen" parameter, one layer further down.
        "MAX_TOKENS": A.MAX_TOKENS,
        "TEMPERATURE": A.TEMPERATURE,
    }


def frozen_surface(mod: types.ModuleType) -> dict:
    return {
        "TRIGGER_WEIGHTS": dict(mod.TRIGGER_WEIGHTS),
        "TRIGGERS_PER_NIGHT": mod.TRIGGERS_PER_NIGHT,
        "MIN_PRICE": mod.MIN_PRICE,
        "MIN_DOLLAR_VOLUME_20D": mod.MIN_DOLLAR_VOLUME_20D,
        "ARMS": tuple(mod.ARMS),
        "REQUEST_MODEL": mod.REQUEST_MODEL,
        "BENCHMARK": mod.BENCHMARK,
        "NIGHTLY_MAX_USD": mod.NIGHTLY_MAX_USD,
        "NIGHTLY_MAX_CALLS": mod.NIGHTLY_MAX_CALLS,
        "MAX_TOKENS": mod.MAX_TOKENS,
        "TEMPERATURE": mod.TEMPERATURE,
    }


def diff_against_frozen(mod: types.ModuleType) -> dict:
    """Field-by-field disagreement between the runtime and the registered rule."""
    rt, fz = runtime_surface(), frozen_surface(mod)
    return {k: {"runtime": rt[k], "frozen": fz[k]}
            for k in fz if rt[k] != fz[k]}


def verify_or_refuse() -> dict:
    """Called before a night can construct a REAL vendor call.

    `OPT_OUT_ENV` is deliberately not consulted. A context that cannot read the
    pre-registration cannot spend money against it — that is the whole point,
    and letting an environment variable wave it through would rebuild the skip
    one layer down, which is the exact bug this trial already paid for once.
    """
    mod = load_frozen_config(allow_opt_out=False)
    assert mod is not None                       # allow_opt_out=False guarantees
    drift = diff_against_frozen(mod)
    if drift:
        raise FrozenPreregDrifted(
            f"the runtime disagrees with the registered rule on "
            f"{sorted(drift)}: {drift}. Refusing to start a paying night — an "
            f"accrual under unregistered parameters is not the trial that was "
            f"pre-registered, and no amount of nights fixes that afterwards.")
    return frozen_surface(mod)
