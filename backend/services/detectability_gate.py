"""Planted-world detectability gate — the declared precondition for TOURNAMENT-2.

ROADMAP_POSITION_2026-08-22, next-sessions item 3: "no TOURNAMENT-2 registered
run counts until the instrument demonstrably recovers its declared effect size
in synthetic worlds (including a heteroskedastic-noise world)."

TOURNAMENT-1's sensitivity worlds measured the instrument BLIND below planted
IC 0.03 — and nothing enforced that fact: the planted receipts were written
and no code path read them. A tournament could have been registered and run
tomorrow with the blindness receipt sitting right next to its panel. This
module is the enforcement: the registered runner calls `assert_detectable`
and either proceeds past a PASS or is refused.

Semantics (canon: a guard DERIVES what it checks or refuses):

- a missing receipt is a REFUSAL, never a pass — a check that did not run is
  not a check that passed;
- a receipt whose `panel_hash` differs from the panel under test is a
  REFUSAL — detectability demonstrated on panel-1 licenses nothing about
  panel-2;
- a receipt whose planted effect exceeds the effect size the caller claims
  to bound is a REFUSAL — recovering a 0.05 world says nothing about 0.03;
- recovery is demonstrated, per world, when the best full-information arm's
  contrast-vs-floor mean reaches `min_recovery x planted IC` AND its CI
  excludes zero. Best-of-arms is deliberate: the licensed claim is "SOME arm
  of this instrument can see an effect this size", which is exactly what a
  subsequent null verdict then bounds.

`declared_ic` and `min_recovery` have NO defaults: they are the prereg's
numbers, and a default here would be the quietly permissive answer this
contract exists to stop. The planted receipts are SENSITIVITY_WORLD
artifacts — never market evidence — and so is everything this module emits.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

#: The worlds a registered run must have demonstrated recovery in. The
#: heteroskedastic world is required by name: the homoskedastic worlds
#: could not test the z-label hypothesis, and a gate that omitted the world
#: where real per-month dispersion loads on both signal and noise would
#: certify detectability in a market that does not exist.
REQUIRED_WORLDS: tuple[str, ...] = ("linear", "linear_dense", "linear_hetero")

RECEIPT_TEMPLATE = "tournament_planted_{world}.json"


class DetectabilityRefused(RuntimeError):
    """An input the gate needed is absent, mismatched, or undeclared —
    or the instrument failed to demonstrate recovery. Either way the
    registered run it guards must not proceed."""


def _load_receipt(receipt_dir: Path, world: str) -> dict:
    path = Path(receipt_dir) / RECEIPT_TEMPLATE.format(world=world)
    if not path.exists():
        raise DetectabilityRefused(
            f"no planted-world receipt for '{world}' at {path} — the "
            f"sensitivity run has not happened on this panel, and a check "
            f"that did not run is not a check that passed")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise DetectabilityRefused(
            f"planted-world receipt for '{world}' is unreadable: {exc}") from exc
    if receipt.get("mode") != "SENSITIVITY_WORLD":
        raise DetectabilityRefused(
            f"'{world}' receipt is not stamped SENSITIVITY_WORLD "
            f"(mode={receipt.get('mode')!r}) — refusing to read it as one")
    return receipt


def evaluate_world(receipt: dict, *, panel_hash: str, declared_ic: float,
                   min_recovery: float) -> dict[str, Any]:
    """One world's verdict. Refuses on missing/mismatched inputs; a world
    that RAN and failed to recover returns ``passed: False`` (that is a
    finding, not a missing input)."""
    world = receipt.get("world", "<unstamped>")
    got_hash = receipt.get("panel_hash")
    if not got_hash or got_hash != panel_hash:
        raise DetectabilityRefused(
            f"'{world}' receipt carries panel_hash {got_hash!r} but the panel "
            f"under test is {panel_hash!r} — detectability on another panel "
            f"licenses nothing here")
    target = (receipt.get("planted") or {}).get("target_ic")
    if not isinstance(target, (int, float)) or target <= 0:
        raise DetectabilityRefused(
            f"'{world}' receipt declares no positive planted target_ic")
    if target > declared_ic + 1e-12:
        raise DetectabilityRefused(
            f"'{world}' planted IC {target} exceeds the declared effect size "
            f"{declared_ic} the run claims to bound — recovering a larger "
            f"world says nothing about a smaller one")
    full_arms = {k: v for k, v in (receipt.get("contrasts") or {}).items()
                 if k.startswith("full_")}
    if not full_arms:
        raise DetectabilityRefused(
            f"'{world}' receipt carries no full_* contrast-vs-floor arms")
    best_name, best_mean, best_ci_lo = None, None, None
    for name, entry in full_arms.items():
        c = entry.get("contrast") or {}
        mean, ci_lo = c.get("mean"), c.get("ci_lo")
        if not isinstance(mean, (int, float)) or not isinstance(ci_lo, (int, float)):
            raise DetectabilityRefused(
                f"'{world}' arm '{name}' lacks a finite mean/ci_lo — the "
                f"recovery it would demonstrate was never computed")
        if best_mean is None or mean > best_mean:
            best_name, best_mean, best_ci_lo = name, mean, ci_lo
    recovery_frac = best_mean / target
    passed = (best_mean >= min_recovery * target) and (best_ci_lo > 0)
    return {
        "world": world,
        "target_ic": target,
        "best_arm": best_name,
        "recovered_mean": best_mean,
        "ci_lo": best_ci_lo,
        "recovery_frac": recovery_frac,
        "min_recovery": min_recovery,
        "passed": passed,
    }


def evaluate_detectability(receipt_dir: Path | str, *, panel_hash: str,
                           declared_ic: float, min_recovery: float,
                           required_worlds: Sequence[str] = REQUIRED_WORLDS,
                           ) -> dict[str, Any]:
    """Full gate evaluation: PASS only when EVERY required world recovered.

    Returns a receipt-shaped dict (``status`` PASS/FAIL plus per-world
    detail); refuses when any input it needs is absent or mismatched.
    """
    if not required_worlds:
        raise DetectabilityRefused(
            "an empty required-worlds set would pass vacuously — the most "
            "permissive answer a missing input can give")
    if not isinstance(declared_ic, (int, float)) or declared_ic <= 0:
        raise DetectabilityRefused("declared_ic must be a positive number "
                                   "declared by the prereg, not defaulted")
    if not isinstance(min_recovery, (int, float)) or not 0 < min_recovery <= 1:
        raise DetectabilityRefused("min_recovery must be in (0, 1], declared "
                                   "by the prereg, not defaulted")
    receipt_dir = Path(receipt_dir)
    if not receipt_dir.is_dir():
        raise DetectabilityRefused(
            f"receipt directory {receipt_dir} does not exist — no sensitivity "
            f"world has run on this panel")
    worlds = [evaluate_world(_load_receipt(receipt_dir, w),
                             panel_hash=panel_hash, declared_ic=declared_ic,
                             min_recovery=min_recovery)
              for w in required_worlds]
    status = "PASS" if all(w["passed"] for w in worlds) else "FAIL"
    return {
        "gate": "PLANTED_WORLD_DETECTABILITY",
        "mode": "SENSITIVITY_WORLD",
        "status": status,
        "panel_hash": panel_hash,
        "declared_ic": declared_ic,
        "min_recovery": min_recovery,
        "required_worlds": list(required_worlds),
        "worlds": worlds,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def assert_detectable(receipt_dir: Path | str, *, panel_hash: str,
                      declared_ic: float, min_recovery: float,
                      required_worlds: Sequence[str] = REQUIRED_WORLDS,
                      ) -> dict[str, Any]:
    """The enforcement point a registered runner calls before its run counts.

    Returns the PASS evaluation; raises `DetectabilityRefused` naming the
    blind world(s) otherwise, so the refusal reaches the operator with the
    number that caused it.
    """
    result = evaluate_detectability(receipt_dir, panel_hash=panel_hash,
                                    declared_ic=declared_ic,
                                    min_recovery=min_recovery,
                                    required_worlds=required_worlds)
    if result["status"] != "PASS":
        blind = [f"{w['world']} (best {w['best_arm']} recovered "
                 f"{w['recovered_mean']:+.4f} of planted {w['target_ic']}, "
                 f"ci_lo {w['ci_lo']:+.4f})"
                 for w in result["worlds"] if not w["passed"]]
        raise DetectabilityRefused(
            "the instrument did not demonstrate recovery of the declared "
            f"effect size {declared_ic} — blind world(s): {'; '.join(blind)}. "
            "No registered run counts on this panel until it does.")
    return result


if __name__ == "__main__":  # pragma: no cover — thin CLI over the library
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--receipt-dir", required=True)
    p.add_argument("--panel-hash", required=True)
    p.add_argument("--declared-ic", type=float, required=True)
    p.add_argument("--min-recovery", type=float, required=True)
    a = p.parse_args()
    try:
        out = evaluate_detectability(a.receipt_dir, panel_hash=a.panel_hash,
                                     declared_ic=a.declared_ic,
                                     min_recovery=a.min_recovery)
    except DetectabilityRefused as exc:
        raise SystemExit(f"REFUSED: {exc}")
    print(json.dumps(out, indent=2))
    raise SystemExit(0 if out["status"] == "PASS" else 1)
