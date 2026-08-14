"""Load the frozen INTERNET-INVESTIGATOR-FWD-1 pre-registration config.

WHY THIS IS NOT A `pytest.skip`
==============================
It used to be. `test_investigator_triggers.py` checked that the runtime copy of
the trigger rule matched the frozen config in the `Aegis module` sibling tree,
and did this when the sibling was absent:

    if not cfg.exists():
        pytest.skip("Aegis module not present in this checkout")

A skip is green. So on any checkout without the sibling — which is every CI
container that clones one repo — the single assertion standing between "the
trial ran the registered rule" and "the trial ran some other rule" reported
success while executing nothing. The trial is about to spend real money on a
40-night accrual whose validity rests on that rule being the registered one.

So the default is now FAILURE, and the escape hatch is explicit, named, and
prints why it fired. A context that genuinely has no sibling tree (a frontend
build, a prod image) must SAY so; it can no longer be inferred from a missing
directory, because "missing directory" is also what a broken checkout looks
like.

This is the same lesson as the tool layer's, one level up: an absent thing and
an unavailable thing must not arrive as the same value.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import types

#: Set to "1" ONLY in a context that legitimately has no `Aegis module` sibling.
#: It is read once, printed when it fires, and never defaults on.
OPT_OUT_ENV = "AEGIS_IIF1_PREREG_ABSENT_OK"

CONFIG_PATH = (pathlib.Path(__file__).resolve().parents[3] / "Aegis module"
               / "scripts" / "iif1_config.py")


class FrozenPreregMissing(RuntimeError):
    """The frozen pre-registration could not be read. Never a skip."""


def load_frozen_config() -> types.ModuleType | None:
    """The frozen config module, or `None` iff the opt-out is explicitly set.

    Raises `FrozenPreregMissing` when the config is absent and no opt-out was
    declared — a loud, conspicuous failure rather than a green SKIP.
    """
    if CONFIG_PATH.exists():
        spec = importlib.util.spec_from_file_location("iif1_config",
                                                      CONFIG_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)                            # type: ignore
        return mod

    if os.environ.get(OPT_OUT_ENV) == "1":
        print(f"\n*** {OPT_OUT_ENV}=1 — the IIF-1 frozen-config consistency "
              f"check DID NOT RUN in this checkout. The runtime trigger rule, "
              f"arms, observables and budget ceilings are UNVERIFIED against "
              f"the pre-registration. This is acceptable only where no "
              f"accrual happens.\n")
        return None

    raise FrozenPreregMissing(
        f"the frozen IIF-1 pre-registration config is missing at "
        f"{CONFIG_PATH}.\n\n"
        f"This check is what guarantees the trial runs the rule that was "
        f"registered. It is not optional before paid accrual, and it will not "
        f"downgrade itself to a skip: a missing sibling tree and a correct "
        f"sibling tree must not both report green.\n\n"
        f"Either check out the `Aegis module` sibling repo, or — if this "
        f"context genuinely never accrues — set {OPT_OUT_ENV}=1 to declare "
        f"that explicitly.")
