"""
Portfolio factory — the same evidence, several explicit risk budgets
====================================================================

Ranking names is not building a portfolio. This turns a ranked list from
`recommendation.py` into weights under archetypes that differ ONLY in their
declared risk budget, never in the evidence they are allowed to use.

Two rules the programme paid for
--------------------------------

**Equal weight is the control, in every comparison.** PF-2 found that copying
the winner loses to equal-weighting, and ARENA-1 put a randomly-picking book
4th of 384. Any weighting scheme that cannot beat EW on the same names is
complexity with no payer, and the factory reports the comparison rather than
quietly shipping the clever one.

**Risk and evidence are separate dimensions** (Murat's ruling, NIGHT-10). An
archetype may take more volatility; it may not take more *credulity*. Every
archetype draws from the same `Recommendation` objects and the same registry
gates, so AGGRESSIVE differs from BALANCED in concentration and volatility
tolerance, never in what counts as evidence.

On Kelly
--------

Fractional Kelly is offered, and it is fed a **shrunk** expected return with a
hard cap, never a raw mu/sigma^2 from a noisy point estimate. Where no
calibrated expected return exists — which is the current state of this
programme for every picker it permits — the Kelly archetypes are **refused**
rather than fed a ranking score dressed as a return. A ranking score is an
ordering; Kelly needs a magnitude, and inventing one is how a scoring bug
becomes a position size.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Archetype:
    name: str
    max_names: int
    max_weight: float
    weighting: str          # "ew" | "signal" | "inverse_vol" | "risk_parity"
    min_confidence: str     # "NONE" | "LOW" | "MEDIUM" | "HIGH"
    description: str
    needs_calibrated_er: bool = False


ARCHETYPES: tuple[Archetype, ...] = (
    Archetype("OPTIMUS_BALANCED", 20, 0.10, "inverse_vol", "LOW",
              "Diversified, volatility-aware, no single name over 10%."),
    Archetype("OPTIMUS_AGGRESSIVE", 12, 0.20, "signal", "LOW",
              "Concentrated in the strongest evidence; higher volatility is "
              "accepted, weaker evidence is not."),
    Archetype("OPTIMUS_HIGH_CONVICTION", 6, 0.25, "signal", "MEDIUM",
              "Only names with corroborating signals. Small, concentrated."),
    Archetype("OPTIMUS_DIVERSIFIED_ALPHA", 40, 0.05, "ew", "LOW",
              "Wide and flat — breadth beats concentration (NIGHT-1)."),
    Archetype("OPTIMUS_LOW_TURNOVER", 20, 0.10, "ew", "LOW",
              "Equal weight, annual clock. Annual beat monthly by +2.43%/yr "
              "in PF-6; churn is the tax nobody budgets for."),
    Archetype("CONTROL_EQUAL_WEIGHT", 20, 0.10, "ew", "NONE",
              "THE CONTROL. Equal weight over the eligible set, no ranking "
              "used. Every archetype above must beat this to justify itself."),
    Archetype("OPTIMUS_MAX_GROWTH", 10, 0.30, "kelly", "MEDIUM",
              "Fractional Kelly on shrunk expected returns.",
              needs_calibrated_er=True),
)

_CONF_ORDER = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}

#: Kelly is never fed a raw point estimate. Even with a calibrated ER, the
#: fraction is capped and the ER is shrunk toward zero first.
KELLY_FRACTION = 0.25
KELLY_ER_SHRINK = 0.50


class ArchetypeRefused(RuntimeError):
    """An archetype cannot be built from the evidence available. Not a bug."""


def _eligible(recs: list[Any], arch: Archetype) -> list[Any]:
    floor = _CONF_ORDER[arch.min_confidence]
    out = [r for r in recs
           if r.ranking_score > 0
           and r.evidence_grade != "NO_EVIDENCE"
           and _CONF_ORDER.get(r.confidence, 0) >= floor]
    return out[:arch.max_names]


def _normalise(raw: dict[str, float], max_weight: float) -> dict[str, float]:
    """Scale to 1.0, then cap, then redistribute the excess — repeatedly.

    One pass is not enough: capping a name pushes weight onto the others, which
    can push THEM over the cap. Iterate to a fixed point, and if the cap cannot
    be satisfied (n * max_weight < 1) say so instead of silently returning
    weights that breach it.
    """
    if not raw:
        return {}
    if len(raw) * max_weight < 1.0 - 1e-9:
        raise ArchetypeRefused(
            f"{len(raw)} names cannot fill a book at a {max_weight:.0%} cap — "
            f"the archetype needs at least {math.ceil(1 / max_weight)} names")
    w = {k: max(0.0, v) for k, v in raw.items()}
    total = sum(w.values())
    if total <= 0:
        n = len(w)
        return {k: 1.0 / n for k in w}
    w = {k: v / total for k, v in w.items()}
    for _ in range(50):
        over = {k: v for k, v in w.items() if v > max_weight + 1e-12}
        if not over:
            break
        excess = sum(v - max_weight for v in over.values())
        under = {k: v for k, v in w.items() if v < max_weight - 1e-12}
        if not under:
            break
        pool = sum(under.values())
        for k in over:
            w[k] = max_weight
        for k, v in under.items():
            w[k] = v + excess * (v / pool if pool else 1.0 / len(under))
    total = sum(w.values())
    out = {k: round(v / total, 6) for k, v in w.items()}
    # Rounding 12 weights to 6dp leaves the book summing to 1.000002, which
    # over-allocates by $2 per $1m and leaves a phantom position behind. Put
    # the residual on the SMALLEST weight that can absorb it without breaching
    # the cap, so the correction cannot create a new breach.
    residual = round(1.0 - sum(out.values()), 6)
    if residual:
        for k, _v in sorted(out.items(), key=lambda kv: kv[1]):
            if out[k] + residual <= max_weight + 1e-12 and out[k] + residual >= 0:
                out[k] = round(out[k] + residual, 6)
                break
    return out


def build(recs: list[Any], arch: Archetype,
          *, vols: Optional[dict[str, float]] = None) -> dict:
    """Weights for one archetype. Raises ArchetypeRefused when it cannot be built."""
    if arch.needs_calibrated_er:
        uncalibrated = [r.ticker for r in recs
                        if r.expected_return is None][:5]
        if uncalibrated:
            raise ArchetypeRefused(
                f"{arch.name} needs a CALIBRATED expected return and none "
                f"exists (e.g. {', '.join(uncalibrated)}). A ranking score is "
                f"an ordering, not a magnitude; feeding it to Kelly would turn "
                f"a scoring artefact into a position size.")

    picked = _eligible(recs, arch)
    if not picked:
        raise ArchetypeRefused(
            f"{arch.name}: no candidate clears confidence >= "
            f"{arch.min_confidence} with a positive ranking score")

    vols = vols or {}
    if arch.weighting == "ew" or arch.name.startswith("CONTROL"):
        raw = {r.ticker: 1.0 for r in picked}
    elif arch.weighting == "signal":
        raw = {r.ticker: max(0.0, r.ranking_score) for r in picked}
    elif arch.weighting == "inverse_vol":
        raw = {}
        for r in picked:
            v = vols.get(r.ticker)
            # An unknown volatility is not a low one. Fall back to the
            # cross-sectional median so a missing reading cannot win the book.
            raw[r.ticker] = 1.0 / v if v and v > 0 else 0.0
        known = [v for v in raw.values() if v > 0]
        if not known:
            raise ArchetypeRefused(
                f"{arch.name}: no candidate carries a volatility reading")
        med = sorted(known)[len(known) // 2]
        raw = {k: (v if v > 0 else med) for k, v in raw.items()}
    else:
        raise ArchetypeRefused(f"unknown weighting {arch.weighting!r}")

    weights = _normalise(raw, arch.max_weight)
    return {
        "archetype": arch.name,
        "description": arch.description,
        "weighting": arch.weighting,
        "min_confidence": arch.min_confidence,
        "max_weight": arch.max_weight,
        "n_names": len(weights),
        "weights": weights,
        "names": [
            {"ticker": r.ticker, "weight": weights.get(r.ticker, 0.0),
             "rank": r.rank, "ranking_score": r.ranking_score,
             "confidence": r.confidence, "evidence_grade": r.evidence_grade,
             "expected_return": r.expected_return,
             "expected_return_basis": r.expected_return_basis}
            for r in picked if weights.get(r.ticker, 0.0) > 0
        ],
        "is_control": arch.name.startswith("CONTROL"),
    }


def build_all(recs: list[Any],
              *, vols: Optional[dict[str, float]] = None) -> dict:
    """Every archetype, with refusals recorded rather than swallowed."""
    built, refused = {}, {}
    for arch in ARCHETYPES:
        try:
            built[arch.name] = build(recs, arch, vols=vols)
        except ArchetypeRefused as exc:
            refused[arch.name] = str(exc)
            logger.info("archetype %s REFUSED: %s", arch.name, exc)
    return {
        "built": built, "refused": refused,
        "control": built.get("CONTROL_EQUAL_WEIGHT"),
        "note": ("Every archetype draws on the same evidence and the same "
                 "registry gates; they differ in risk budget only. A refusal "
                 "is a finding about the evidence, not a failure of the "
                 "factory. CONTROL_EQUAL_WEIGHT is the bar the others must "
                 "clear — winner-copying already lost to it once (PF-2)."),
    }
