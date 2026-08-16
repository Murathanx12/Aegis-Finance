"""Quantities computed with hindsight, made structurally unable to be traded.

WHY THIS EXISTS (2026-08-16, from N12)
======================================
N12 compares sizing policies at matched realised volatility:

    scale = ref_vol / pv          # n12_vol_targeted_sizing.py:126

where `pv` is the policy's realised volatility over the **whole sample**. That
is hindsight. As an evaluation normalisation it is not merely acceptable, it is
necessary — without it the table is a statement about average exposure and
nothing else. As a live exposure it is a lie, because no one standing at the
start of the sample knows `pv`.

So the number is legitimate and un-deployable at the same time, and the failure
mode is not that anyone would knowingly deploy it — it is that
`v * scale` is four characters and reads exactly like every other line in a
sizing path.

THE GUARD
=========
`ExPostScale` is deliberately **not a number**. It has no `__mul__`, no
`__float__`, no `__array__`. Multiplying an exposure array by one raises
`TypeError` from numpy itself, at the point of use, with no cooperation from
the author required. Getting the value out means naming what you are doing:

    scale.for_comparison_only()

A comment saying "evaluation only" is a comment. This is the exit code.

WHAT THIS DOES NOT CLAIM
========================
It stops an ex-post scale reaching a live path *through this object*. It does
not stop someone recomputing `ref_vol / pv` inline somewhere else — that is
what `test_ex_post_scale.py::test_no_inline_full_sample_scaling_outside_this_module`
is for.
"""

from __future__ import annotations

from dataclasses import dataclass


class ExPostUsageError(TypeError):
    """Raised when a hindsight quantity is used where a live one is required."""


@dataclass(frozen=True)
class ExPostScale:
    """A scalar computed from data the decision could not have seen.

    Parameters
    ----------
    value:
        The scale itself.
    basis:
        One sentence naming the hindsight. Required — an unexplained ex-post
        quantity is the thing this class exists to prevent, so it may not be
        constructed anonymously.
    """

    value: float
    basis: str

    def __post_init__(self) -> None:
        if not self.basis or not self.basis.strip():
            raise ExPostUsageError(
                "ExPostScale requires `basis`: one sentence naming the "
                "hindsight it is built from. An ex-post quantity nobody had to "
                "justify in words is how one reaches production.")

    # ── the point of the class: it is not a number ─────────────────────────
    def __mul__(self, other):                                    # noqa: D105
        raise ExPostUsageError(_REFUSAL.format(basis=self.basis))

    __rmul__ = __mul__
    __add__ = __mul__
    __radd__ = __mul__
    __truediv__ = __mul__
    __rtruediv__ = __mul__

    def __float__(self) -> float:                                # noqa: D105
        raise ExPostUsageError(_REFUSAL.format(basis=self.basis))

    def __array__(self, *a, **k):                                # noqa: D105
        # numpy asks for this before broadcasting; refusing here is what makes
        # `exposures * scale` fail instead of silently succeeding.
        raise ExPostUsageError(_REFUSAL.format(basis=self.basis))

    def for_comparison_only(self) -> float:
        """The value, for use in an evaluation table and nowhere else.

        Named so that the call site says what it is doing. Every use in the
        repository is greppable by this method name.
        """
        return float(self.value)

    def __repr__(self) -> str:                                   # noqa: D105
        return (f"ExPostScale({self.value:.6g}, "
                f"basis={self.basis!r}) [NOT DEPLOYABLE]")


_REFUSAL = (
    "this is an EX-POST quantity and cannot enter an exposure, weight or "
    "order path. Basis: {basis}. If you are building an evaluation table, "
    "call `.for_comparison_only()` and say so at the call site; if you are "
    "sizing a position, you need a quantity estimable at the decision time, "
    "which this is not."
)


def matched_vol_scale(reference_vol: float, policy_vol: float,
                      *, basis: str) -> ExPostScale:
    """The N12 normalisation, returned as something that cannot be traded.

    `policy_vol` is realised over the whole evaluation sample, so the result is
    hindsight by construction and is typed accordingly.
    """
    if not policy_vol or policy_vol <= 0:
        return ExPostScale(1.0, basis=basis + " (degenerate: policy vol <= 0)")
    return ExPostScale(float(reference_vol) / float(policy_vol), basis=basis)


@dataclass(frozen=True)
class ExPostArray:
    """A vector of hindsight quantities, one per observation.

    Same contract as `ExPostScale`, for the case where the hindsight is
    per-row — a forward realised volatility, a future drawdown depth, the
    outcome-conditional scale used in a decomposition. Arrays are the more
    dangerous case, because `preds * oracle` broadcasts silently and produces a
    plausible table.
    """

    values: object                     # np.ndarray, kept untyped to avoid an
    basis: str                         # import of numpy at module scope

    def __post_init__(self) -> None:
        if not self.basis or not self.basis.strip():
            raise ExPostUsageError(
                "ExPostArray requires `basis`: one sentence naming the "
                "hindsight it is built from.")

    def __mul__(self, other):                                    # noqa: D105
        raise ExPostUsageError(_REFUSAL.format(basis=self.basis))

    __rmul__ = __mul__
    __add__ = __mul__
    __radd__ = __mul__
    __truediv__ = __mul__
    __rtruediv__ = __mul__

    def __array__(self, *a, **k):                                # noqa: D105
        raise ExPostUsageError(_REFUSAL.format(basis=self.basis))

    def __iter__(self):                                          # noqa: D105
        # iteration is the other silent route into a numeric context
        raise ExPostUsageError(_REFUSAL.format(basis=self.basis))

    def for_comparison_only(self):
        """The raw array, for a diagnostic table and nowhere else."""
        return self.values

    def __repr__(self) -> str:                                   # noqa: D105
        n = getattr(self.values, "shape", ("?",))
        return f"ExPostArray(shape={n}, basis={self.basis!r}) [NOT DEPLOYABLE]"


def oracle_scale(realised_forward_scale, *, basis: str) -> ExPostArray:
    """A per-row scale measured over the outcome window the row is predicting.

    This is maximal hindsight: it is the answer's own dispersion. It exists to
    answer *"is the estimator the bottleneck, or the shape model?"* by handing
    a candidate the one thing it cannot know, and it can never be evidence for
    anything a policy would do.
    """
    return ExPostArray(realised_forward_scale, basis=basis)
