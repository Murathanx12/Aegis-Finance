"""The declared gate on RELIABILITY_ROUTER capital authority.

ORDER 27 P2 (`docs/ADJUDICATION_2026-08-22_ORDER_27.md`):

    "RELIABILITY_ROUTER gains no capital authority beyond v1's aggression knob
     until a correlated-worlds battery (hundreds of worlds, clustered by
     decision date, correlated names, regime blocks) passes at <=5% null
     recommendation AND reports null-world capital exposure."

That sentence is a gate only if something reads it. The detectability gate
exists because TOURNAMENT-1's blindness receipts were written and never read;
this module is the same enforcement for the same reason, one layer up: a
future book that wants to size on the router's verdict calls
`assert_router_licensed` and either proceeds past a PASS or is refused.

What it refuses, and why each refusal is a refusal rather than a default:

* a missing or unreadable receipt — a check that did not run is not a check
  that passed;
* a receipt not stamped KNOWN_ANSWER_BATTERY — planted worlds are the only
  thing that can license this, and market evidence cannot;
* a receipt whose router fingerprint differs from the LIVE router's. This is
  the load-bearing one. The fingerprint covers the estimator's SOURCE, not
  just its constants, because the correction that made the router passable
  lives in a function body: a receipt measured with `cluster_adjust` ON
  licenses nothing while the module runs with it OFF, and that is precisely
  what keeps the flip attended instead of implied;
* too few null worlds — "0 of 20" bounds a 5% claim to nothing (rule of
  three), so the receipt must carry hundreds of worlds before its rate is
  allowed to mean what it says;
* a null recommendation rate above the declared bar;
* absent capital-exposure numbers — the ORDER requires them REPORTED, and a
  receipt that omits the economic metric has not answered the question the
  verdict rate cannot;
* recovery below the declared floor. This condition is NOT in ORDER 27, and
  it is stated as an addition rather than smuggled: a gate that binds only
  the false-positive rate is passed perfectly by a router that never
  recommends anything, so without it the gate could license a dead
  instrument. It can only ever make the gate STRICTER;
* a harmful-leak rate above the declared bar. v1's battery declared this
  ZERO; the correlated worlds show zero is not attainable — a truly harmful
  actor sometimes looks fine on a few dozen independent decisions — so the
  bar is a RATE with an interval, which is the ORDER's own instruction
  ("quote the cost rate or don't quote the count") applied to the metric that
  first prompted it.

Nothing here is market evidence. The receipt this reads is a synthetic
planted-world artifact and says so.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.arena import reliability, trust_router

#: ORDER 27 P2, verbatim: the false-positive bar and "hundreds of worlds".
MAX_NULL_RECOMMENDATION_RATE = 0.05
MIN_NULL_WORLDS = 200

#: NOT from ORDER 27 — added here so the gate cannot be passed by a router
#: that never recommends anything, and so a measurably harmful actor's claim
#: on capital is bounded by a measured rate rather than an unattainable zero.
#: Both make the gate stricter than the ORDER; neither can loosen it.
MIN_EDGE_RECOVERY_RATE = 0.70
MAX_HARMFUL_LEAK_RATE = 0.05

DEFAULT_RECEIPT = (Path(__file__).resolve().parents[2] / "backend" / "data" /
                   "optimus" / "g1_correlated_battery.json")


class RouterCapitalRefused(RuntimeError):
    """The router has not demonstrated, on the battery that governs it, that
    it can be trusted with capital — or the evidence that it did is missing,
    stale, or describes a different router. Either way the caller must not
    size on its verdict."""


def live_router_fingerprint(cluster_adjust: bool | None = None) -> dict:
    """What a passing receipt would be licensing: THIS router, as it runs.

    The estimator is fingerprinted by source because every correction this
    battery measured — the design-effect division, the pooled actor-level
    count, the Bonferroni trust bar, the below-prior fallback — changes
    behaviour without moving a declared constant. A fingerprint of constants
    alone would keep licensing across exactly the edits that matter.
    """
    if cluster_adjust is None:
        cluster_adjust = trust_router.CLUSTER_ADJUST_DEFAULT
    src = "".join(inspect.getsource(f) for f in
                  (trust_router._effective_n, trust_router._cell_n_eff,
                   trust_router._hierarchy, trust_router.trust_weights,
                   trust_router.backoff_estimate, trust_router._standard_error,
                   trust_router.edge_z, reliability.design_effect,
                   reliability._actor_clustering))
    return {
        "router_version": trust_router.ROUTER_VERSION,
        "shrink_k": trust_router.SHRINK_K,
        "prior": trust_router.POPULATION_PRIOR,
        "edge_z": trust_router.EDGE_Z,
        "edge_alpha": trust_router.EDGE_ALPHA,
        "evidence_floor_n": trust_router.EVIDENCE_FLOOR_N,
        "cluster_adjust": bool(cluster_adjust),
        "cluster_adjust_default": trust_router.CLUSTER_ADJUST_DEFAULT,
        "correlation_adjusted":
            trust_router._banner(bool(cluster_adjust))["correlation_adjusted"],
        "estimator_source_sha": hashlib.sha256(src.encode()).hexdigest()[:16],
    }


#: The fingerprint fields that must agree for a receipt to license the live
#: router. `cluster_adjust_default` is deliberately excluded from the compared
#: set and compared separately: a receipt measured under a setting the module
#: does not run under is the exact case this gate exists to catch.
_FINGERPRINT_KEYS = ("router_version", "shrink_k", "prior", "edge_z",
                     "edge_alpha", "evidence_floor_n", "cluster_adjust",
                     "estimator_source_sha")


def _load(receipt_path: Path | str) -> dict:
    path = Path(receipt_path)
    if not path.exists():
        raise RouterCapitalRefused(
            f"no G1 correlated-worlds receipt at {path} — the battery that "
            f"governs router capital authority has not run against this "
            f"router, and a check that did not run is not a check that passed")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RouterCapitalRefused(
            f"G1 battery receipt at {path} is unreadable: {exc}") from exc
    if receipt.get("mode") != "KNOWN_ANSWER_BATTERY":
        raise RouterCapitalRefused(
            f"receipt at {path} is not stamped KNOWN_ANSWER_BATTERY "
            f"(mode={receipt.get('mode')!r}) — refusing to read it as one")
    if receipt.get("gate") != "ROUTER_CAPITAL_AUTHORITY":
        raise RouterCapitalRefused(
            f"receipt at {path} governs {receipt.get('gate')!r}, not router "
            f"capital authority")
    return receipt


def _check_fingerprint(receipt: dict) -> dict:
    got = receipt.get("router") or {}
    live = live_router_fingerprint(got.get("cluster_adjust"))
    diffs = {k: (got.get(k), live.get(k)) for k in _FINGERPRINT_KEYS
             if got.get(k) != live.get(k)}
    if diffs:
        detail = "; ".join(f"{k}: receipt {r!r} vs live {lv!r}"
                           for k, (r, lv) in sorted(diffs.items()))
        raise RouterCapitalRefused(
            f"the receipt measured a different router than the one running — "
            f"{detail}. Evidence about another estimator licenses nothing "
            f"here.")
    if bool(got.get("cluster_adjust")) != bool(
            trust_router.CLUSTER_ADJUST_DEFAULT):
        raise RouterCapitalRefused(
            f"the receipt measured the router with cluster_adjust="
            f"{got.get('cluster_adjust')} but the module runs with "
            f"CLUSTER_ADJUST_DEFAULT={trust_router.CLUSTER_ADJUST_DEFAULT} — "
            f"a battery passed under a setting that is not switched on is a "
            f"description of a router nobody is running. Flipping that default "
            f"is an attended decision (it moves a live book's sizing).")
    return live


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and value == value and \
        value not in (float("inf"), float("-inf"))


def evaluate_router_license(
        receipt_path: Path | str = DEFAULT_RECEIPT, *,
        max_null_rate: float = MAX_NULL_RECOMMENDATION_RATE,
        min_worlds: int = MIN_NULL_WORLDS,
        min_edge_recovery: float = MIN_EDGE_RECOVERY_RATE,
        max_harmful_leak_rate: float = MAX_HARMFUL_LEAK_RATE) -> dict[str, Any]:
    """Full evaluation. Refuses on absent/mismatched inputs; returns a
    receipt-shaped dict with `status` PASS/FAIL when the battery RAN and its
    numbers simply did or did not clear the bars (that is a finding)."""
    receipt = _load(receipt_path)
    live = _check_fingerprint(receipt)

    n_worlds = receipt.get("n_null_worlds") or 0
    if not isinstance(n_worlds, int) or n_worlds < min_worlds:
        raise RouterCapitalRefused(
            f"the battery ran {n_worlds} null worlds, below the declared "
            f"minimum {min_worlds} — at that count the measured rate does not "
            f"bound the true one tightly enough to mean {max_null_rate:.0%} "
            f"(rule of three)")

    rate = receipt.get("null_recommendation_rate")
    if not _finite(rate):
        raise RouterCapitalRefused(
            "the receipt carries no finite null_recommendation_rate — the "
            "number the gate binds was never computed")
    exposure_fields = ("null_capital_exposure_deployed",
                       "null_capital_exposure_given_deployed",
                       "null_capital_exposure_fallback")
    missing = [f for f in exposure_fields if not _finite(receipt.get(f))]
    if missing:
        raise RouterCapitalRefused(
            f"the receipt does not report null-world capital exposure "
            f"({', '.join(missing)}) — ORDER 27 requires the economic metric "
            f"reported, and a verdict rate does not answer it")

    recovery = receipt.get("edge_recovery_rate")
    if not _finite(recovery):
        raise RouterCapitalRefused(
            "the receipt carries no finite edge_recovery_rate — without it a "
            "router that never recommends anything passes this gate perfectly")
    leak_worlds = receipt.get("harmful_leak_worlds")
    harm_arm = (receipt.get("arms") or {}).get("harmful") or {}
    n_harm = harm_arm.get("n_worlds") or 0
    if not isinstance(leak_worlds, int) or not n_harm:
        raise RouterCapitalRefused(
            "the receipt carries no harmful-world arm — the leak rate the "
            "gate bounds was never measured")
    leak_rate = leak_worlds / n_harm

    checks = {
        "null_recommendation_rate": {
            "value": rate, "bar": max_null_rate, "passed": rate <= max_null_rate,
            "ci95": receipt.get("null_recommendation_rate_ci95")},
        "edge_recovery_rate": {
            "value": recovery, "bar": min_edge_recovery,
            "passed": recovery >= min_edge_recovery},
        "harmful_leak_rate": {
            "value": round(leak_rate, 4), "bar": max_harmful_leak_rate,
            "passed": leak_rate <= max_harmful_leak_rate,
            "leak_worlds": leak_worlds, "n_harmful_worlds": n_harm},
    }
    status = "PASS" if all(c["passed"] for c in checks.values()) else "FAIL"
    return {
        "gate": "ROUTER_CAPITAL_AUTHORITY",
        "mode": "KNOWN_ANSWER_BATTERY",
        "status": status,
        "receipt": str(receipt_path),
        "battery": receipt.get("battery"),
        "router": live,
        "n_null_worlds": n_worlds,
        "checks": checks,
        "capital_exposure": {f: receipt.get(f) for f in exposure_fields},
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def assert_router_licensed(receipt_path: Path | str = DEFAULT_RECEIPT,
                           **kwargs) -> dict[str, Any]:
    """The enforcement point. Returns the PASS evaluation, or raises
    `RouterCapitalRefused` naming the number that failed."""
    result = evaluate_router_license(receipt_path, **kwargs)
    if result["status"] != "PASS":
        failed = "; ".join(
            f"{name} = {c['value']} against bar {c['bar']}"
            for name, c in result["checks"].items() if not c["passed"])
        raise RouterCapitalRefused(
            f"RELIABILITY_ROUTER has no capital authority beyond v1's "
            f"aggression knob: {failed}. ORDER 27 P2 binds until the "
            f"correlated-worlds battery passes.")
    return result


if __name__ == "__main__":  # pragma: no cover — thin CLI over the library
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--receipt", default=str(DEFAULT_RECEIPT))
    a = p.parse_args()
    try:
        out = evaluate_router_license(a.receipt)
    except RouterCapitalRefused as exc:
        raise SystemExit(f"REFUSED: {exc}")
    print(json.dumps(out, indent=2))
    raise SystemExit(0 if out["status"] == "PASS" else 1)
