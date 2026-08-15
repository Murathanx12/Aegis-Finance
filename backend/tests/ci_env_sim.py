"""Opt-in pytest plugin: run the suite the way CI runs it.

    python -m pytest backend/tests/ -m "not slow" -q -p backend.tests.ci_env_sim

WHY (paid for 2026-08-15)
========================
CI checks out ONE repo, so `../Aegis module` — which holds the frozen IIF-1
pre-registration — is genuinely absent there. Two tests silently depended on it
being present, passed on the dev machine across 4,153 tests, and turned CI red.

Because Railway gates deploys on CI, that red build stopped **every** deploy for
three commits: production sat on `5d7ae15` while `a355fa6` was reported shipped.
The §39 timing guard, written specifically to protect a paid night, was not in
production while the report said it was.

The failure mode is not "a test broke". It is that **the green signal on this
machine and the green signal that gates production were measuring different
worlds**, and only one of them was being looked at. This plugin makes the second
world reachable in four minutes without pushing.

It does not replace checking CI. Nothing replaces checking CI.
"""

from __future__ import annotations

import pathlib

#: Somewhere that cannot exist, rather than somewhere that merely does not
#: exist yet — a path under the repo could be created by another test.
_ABSENT = pathlib.Path("/nonexistent-ci-sim/Aegis module/scripts/iif1_config.py")


def pytest_configure(config) -> None:
    from backend.services import iif1_prereg as P
    config._aegis_real_prereg_path = P.CONFIG_PATH
    P.CONFIG_PATH = _ABSENT
    print(f"\n*** ci_env_sim: the `Aegis module` sibling is hidden "
          f"({P.CONFIG_PATH}). Any test that needs it must supply it "
          f"explicitly, as CI forces it to.\n")


def pytest_unconfigure(config) -> None:
    real = getattr(config, "_aegis_real_prereg_path", None)
    if real is not None:
        from backend.services import iif1_prereg as P
        P.CONFIG_PATH = real
