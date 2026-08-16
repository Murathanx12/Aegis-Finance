"""Quantities that may appear in an evaluation table and nowhere else.

WHY THIS IS A PACKAGE AND NOT A MODULE
======================================
`ExPostScale` refuses arithmetic, which stops an accidental
`exposures * scale`. It does **not** stop a later author writing

    exposures * scale.for_comparison_only()

deliberately, having decided the refusal was in the way. A type error catches a
slip. It cannot catch intent, and intent is what a code path six months from
now looks like when someone is trying to make a number line up.

So the guard has two layers:

1. **The type** — `ExPostScale` / `ExPostArray` are not numbers. Slips raise.
2. **The boundary** — hindsight lives in `research_gym.evaluation_only`, and
   `backend/tests/test_ex_post_boundary.py` fails if any deployable module
   imports it, transitively. Reaching for the number now requires adding an
   import that a test refuses.

The boundary is the part that survives a determined author, because it makes
the wrong thing loud rather than merely inconvenient.

WHAT COUNTS AS DEPLOYABLE
=========================
Anything the API can reach: `backend/routers/**` and `backend/services/**`
except this package and the offline research entry points that import it
explicitly. The test owns that list; it is not configuration.
"""

from __future__ import annotations

from backend.services.research_gym.evaluation_only.ex_post import (  # noqa: F401
    ExPostArray,
    ExPostScale,
    ExPostUsageError,
    matched_vol_scale,
    oracle_scale,
)

__all__ = ["ExPostArray", "ExPostScale", "ExPostUsageError",
           "matched_vol_scale", "oracle_scale"]
