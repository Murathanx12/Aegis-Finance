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

AND IT WAS INCOMPLETE ON ITS FIRST DAY (found 2026-08-15, one day later)
========================================================================
The first version hid the sibling and stopped there. `.github/workflows/ci.yml`
also exports `AEGIS_IIF1_PREREG_ABSENT_OK: "1"`, which the consistency checks
honour and `verify_or_refuse` deliberately ignores. Without it this plugin was
STRICTER than CI — eleven prereg-consistency tests failed here and pass there —
so a tool built to end "two green signals, two different worlds" was quietly
introducing a **third** world, and the extra failures it produced looked exactly
like real ones.

Both halves of CI's environment are set here now, and the workflow file is the
single source both read from.

AND IT WAS INCOMPLETE A SECOND WAY (found 2026-08-16, by another red CI)
=======================================================================
CI's pytest step exports `AEGIS_IIF1_PREREG_ABSENT_OK` and **nothing else** — no
secrets. This machine has FRED_API_KEY, FINNHUB_API_KEY and the rest in `.env`,
so `api_keys.has("fred")` is True here and False there. Four new FRED tests
passed in this simulated world and turned CI red on `4d16013`.

Same defect as the sibling repo, one dimension over: the plugin modelled what CI
*hides* and not what CI *lacks*. Keys are now blanked and `config.api_keys` is
rebuilt from the blanked environment, because it is a module-level singleton
constructed at import — clearing `os.environ` alone would not have moved it,
which is its own instance of "where is this value actually read?".
"""

from __future__ import annotations

import os
import pathlib

#: Somewhere that cannot exist, rather than somewhere that merely does not
#: exist yet — a path under the repo could be created by another test.
_ABSENT = pathlib.Path("/nonexistent-ci-sim/Aegis module/scripts/iif1_config.py")

#: Exactly what `.github/workflows/ci.yml` exports for the pytest step. A key
#: here that CI does not set (or one CI sets that is missing here) is the same
#: defect this plugin exists to prevent, one level up.
_CI_ENV = {"AEGIS_IIF1_PREREG_ABSENT_OK": "1"}

#: Secrets CI does NOT have. Blanked rather than deleted, so anything reading
#: them sees the same empty string CI's runner produces.
_CI_ABSENT_KEYS = (
    "FRED_API_KEY",
    "FINNHUB_API_KEY",
    "FMP_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "POLYGON_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
)


def pytest_configure(config) -> None:
    from backend import config as _cfg
    from backend.services import iif1_prereg as P
    config._aegis_real_prereg_path = P.CONFIG_PATH
    config._aegis_real_env = {k: os.environ.get(k)
                              for k in (*_CI_ENV, *_CI_ABSENT_KEYS)}
    P.CONFIG_PATH = _ABSENT
    os.environ.update(_CI_ENV)
    for k in _CI_ABSENT_KEYS:
        os.environ[k] = ""
    # `api_keys` is built from the environment at IMPORT, so blanking os.environ
    # is not enough on its own. Nor is rebinding `config.api_keys`: every
    # service does `from backend.config import api_keys` and holds the ORIGINAL
    # object, so a new one would never be seen. The singleton is mutated IN
    # PLACE, which is the only version every reference actually observes.
    config._aegis_real_api_keys = {f: getattr(_cfg.api_keys, f)
                                   for f in _cfg.api_keys.__dataclass_fields__}
    for field_name in config._aegis_real_api_keys:
        setattr(_cfg.api_keys, field_name, "")
    print(f"\n*** ci_env_sim: the `Aegis module` sibling is hidden "
          f"({P.CONFIG_PATH}), {sorted(_CI_ENV)} are set as CI sets them, and "
          f"{len(_CI_ABSENT_KEYS)} API keys are blanked because CI has no "
          f"secrets. Any test that needs the sibling or a key must supply it "
          f"explicitly, as CI forces it to.\n")


def pytest_unconfigure(config) -> None:
    real = getattr(config, "_aegis_real_prereg_path", None)
    if real is not None:
        from backend.services import iif1_prereg as P
        P.CONFIG_PATH = real
    for k, v in (getattr(config, "_aegis_real_env", None) or {}).items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    real_keys = getattr(config, "_aegis_real_api_keys", None)
    if real_keys:
        from backend import config as _cfg
        for field_name, value in real_keys.items():
            setattr(_cfg.api_keys, field_name, value)
