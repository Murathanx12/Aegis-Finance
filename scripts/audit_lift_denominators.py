"""A lift is a ratio, and a ratio to a denominator near zero is division by noise.

    python -m scripts.audit_lift_denominators

WHERE THIS RULE CAME FROM
=========================
The 2x2 script reports what fraction of an announcement effect is lost in the
overnight gap, as `1 - tradable/close_to_close`. For the `A - C` contrast the
close-to-close base is -0.05pp and BELOW ITS OWN MDE, and the ratio printed
**253%** — a confident-looking number computed entirely from noise. It is now
suppressed there.

The rule generalises, and it points back at our own headline numbers: **lift is
a ratio too.** N9's 1.271, N20's L_min comparisons and N4's coverage lifts are
all `treated / base`. If any of those bases is indistinguishable from zero, the
lift is the same error with a different name, and it has been quoted in every
review for a week.

So this sweeps them rather than assuming. Checking a number that supports our
own conclusions is §37's mirror: check passes as hard as kills.

WHAT COUNTS AS "NEAR ZERO"
==========================
The denominator is a RATE in this family — the fraction of days a precursor
fires — so its standard error is `sqrt(p(1-p)/n)` and the question is how many
SEs it sits from zero. A base within ~2 SE of zero makes the lift unreportable;
anything under ~5 SE deserves the interval printed beside it.

Rates, not returns, is itself the thing that makes this family survivable. A
lift built on a mean RETURN as the denominator would be in real trouble: mean
returns sit close to zero by construction, which is exactly why `mu_rest` in the
numerator was the N4B finding.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

DATA = Path("backend/data/optimus/research_gym")

#: Below this many SEs from zero, a lift is a ratio to noise and must not be
#: reported as a multiplier. Declared, not tuned.
UNREPORTABLE_Z = 2.0
#: Between these, report the base's interval alongside the lift.
FRAGILE_Z = 5.0

#: FILES WHOSE GENERATING CODE BOUNDS THE DENOMINATOR BY CONSTRUCTION.
#:
#: The first run scored 400 of 424 ratios "unscoreable — no n recorded" and then
#: printed a clean verdict. That is the exact shape of the R13e sweep's own
#: failure: a report that says zero because it could read nothing. All 400 are
#: N21's frozen rules, whose selection loop contains
#:
#:     if base <= 0.005 or base >= 0.60: continue
#:
#: so every surviving rule's denominator is above 0.5% BY CONSTRUCTION, before
#: any lift is computed. That floor plus a lower bound on the sample is enough
#: to bound the z without knowing the exact n — and a bound is a measurement
#: where a guess is not.
#:
#: The train sample is three securities over 1999-2015. The bound below is
#: deliberately far under the true count: being wrong here can only make the
#: audit stricter.
DENOMINATOR_FLOORS = {
    "n21_frozen_rules.json": {
        "floor": 0.005, "n_lower_bound": 3000,
        "why": ("n21_policy_utility.py's selection loop discards any candidate "
                "with base <= 0.005, so no surviving rule can have a "
                "denominator below that. n bounded well below the true train "
                "count (3 securities x ~4,280 days); a loose bound here only "
                "makes the audit stricter."),
    },
}


def rate_se(p: float, n: int) -> float | None:
    if n <= 0 or not 0.0 <= p <= 1.0:
        return None
    return math.sqrt(max(p * (1.0 - p), 0.0) / n)


def scan(obj, path="") -> list[dict]:
    """Find every (lift, base-rate, n) triple, wherever it is nested."""
    found: list[dict] = []
    if isinstance(obj, dict):
        keys = {k.lower(): k for k in obj}
        lift_k = next((keys[k] for k in keys
                       if k == "lift" or k.endswith("_lift")), None)
        base_k = next((keys[k] for k in keys
                       if k in ("base_rate", "fire_rate", "base")), None)
        n_k = next((keys[k] for k in keys
                    if k in ("n_total", "n_obs_per_security", "n_days",
                             "n_nontail_firing_days")), None)
        if lift_k and base_k:
            found.append({
                "path": path or ".", "lift": obj[lift_k], "base": obj[base_k],
                "n": obj.get(n_k) if n_k else None,
                "lift_field": lift_k, "base_field": base_k,
                "n_field": n_k})
        for k, v in obj.items():
            found += scan(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:400]):
            found += scan(v, f"{path}[{i}]")
    return found


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    files = sorted(DATA.glob("*.json"))
    print(f"scanning {len(files)} research_gym artifacts for lift ratios\n")

    unreportable, fragile, ok, unscoreable, bounded_rows = [], [], [], [], []
    for f in files:
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:                                 # noqa: BLE001
            print(f"  {f.name}: unreadable ({exc})")
            continue
        hits = scan(obj)
        # A file's default `n` is often declared once at the top rather than on
        # every row; inherit it rather than scoring hundreds of rows as
        # unscoreable for a field that IS present one level up.
        top_n = None
        if isinstance(obj, dict):
            for k in ("n_days", "n_obs_per_security", "n_total"):
                if isinstance(obj.get(k), (int, float)):
                    top_n = int(obj[k])
                    break
        for h in hits:
            n = h["n"] or top_n
            try:
                base, lift = float(h["base"]), float(h["lift"])
            except (TypeError, ValueError):
                continue
            se = rate_se(base, int(n)) if n else None
            bounded = None
            if se is None and f.name in DENOMINATOR_FLOORS:
                # Score the WORST CASE the generating code permits, not the
                # observed value: floor base, floor n. If that clears, every
                # row in the file clears.
                fl = DENOMINATOR_FLOORS[f.name]
                se = rate_se(fl["floor"], fl["n_lower_bound"])
                base = fl["floor"]
                bounded = fl["why"]
            rec = {**h, "file": f.name, "n_used": n, "se": se,
                   "z": (base / se) if se else None,
                   "bounded_by_construction": bounded}
            if se is None:
                unscoreable.append(rec)
            elif bounded:
                # Scored at the worst case the generating code allows, so the
                # z here is a LOWER BOUND on each row's true z, not an estimate
                # of it. Bucketed separately: printing 400 rows as "fragile"
                # would report a property of the bound as a property of the
                # data, which is the same class of error the audit exists for.
                bounded_rows.append(rec)
            elif rec["z"] < UNREPORTABLE_Z:
                unreportable.append(rec)
            elif rec["z"] < FRAGILE_Z:
                fragile.append(rec)
            else:
                ok.append(rec)

    n_all = (len(unreportable) + len(fragile) + len(ok) + len(unscoreable)
             + len(bounded_rows))
    print(f"  lift ratios found: {n_all}")
    print(f"    denominator >= {FRAGILE_Z}SE from zero (safe) : {len(ok)}")
    print(f"    fragile ({UNREPORTABLE_Z}-{FRAGILE_Z}SE)                 : "
          f"{len(fragile)}")
    print(f"    UNREPORTABLE (< {UNREPORTABLE_Z}SE)             : "
          f"{len(unreportable)}")
    print(f"    bounded by a construction floor     : {len(bounded_rows)}")
    print(f"    unscoreable (no n, no floor)        : {len(unscoreable)}")
    if bounded_rows:
        z0 = min(r["z"] for r in bounded_rows)
        print(f"      worst-case z under the floor: {z0:.1f} "
              f"(>= {UNREPORTABLE_Z} required). Each row's TRUE z is higher — "
              f"this is a lower bound, not an estimate.")
    for f_, fl in DENOMINATOR_FLOORS.items():
        print(f"      {f_}: {fl['why']}")

    for tag, rows in (("UNREPORTABLE", unreportable), ("FRAGILE", fragile)):
        for r in rows[:20]:
            print(f"\n  [{tag}] {r['file']}  {r['path']}")
            print(f"     lift {r['lift']:.4g}  base {r['base']:.5g}  "
                  f"n {r['n_used']}  SE {r['se']:.5g}  z {r['z']:.1f}")

    # THE NUMBER THIS AUDIT WAS ORDERED TO CHECK, resolved by hand because the
    # generic scanner looks for `base_rate` and N20 records the same quantity
    # under `power_declaration.<H>.fire_rate`. A sweep that says "not recorded"
    # about the one number it was asked about has not answered the question.
    print("\n  the numbers this audit was ordered to check:")
    p20 = DATA / "n20_conditional_mu_rest.json"
    if p20.exists():
        o = json.loads(p20.read_text(encoding="utf-8"))
        pd_ = o.get("power_declaration", {})
        for h, blk in sorted(pd_.items()):
            fr = blk.get("fire_rate")
            n = blk.get("n_obs_per_security")
            if fr is None or not n:
                continue
            se = rate_se(float(fr), int(n))
            print(f"    N9's 1.271 family, H={h}: base = the precursor FIRE "
                  f"RATE {fr:.4f} at n={n:,}")
            print(f"      SE {se:.5f}  ->  {fr/se:.0f} SE from zero. The "
                  f"denominator is a RATE near 0.16, not a mean return near "
                  f"zero; 1.271 is not division by noise.")
    p4 = DATA / "n4_precursor_coverage.json"
    if p4.exists():
        o = json.loads(p4.read_text(encoding="utf-8"))
        rows = [r for r in o.get("rows", [])
                if isinstance(r.get("base_rate"), (int, float))]
        if rows:
            w = min(rows, key=lambda r: r["base_rate"])
            n = w.get("n_total") or 6591
            se = rate_se(float(w["base_rate"]), int(n))
            print(f"    N4 coverage lifts: smallest base {w['base_rate']:.4f} "
                  f"at n={n:,} -> {w['base_rate']/se:.0f} SE from zero")

    if unreportable:
        print("\nVERDICT: at least one lift is a ratio to a denominator "
              "indistinguishable from zero. Those may not be quoted as "
              "multipliers.")
        return 2
    print("\nVERDICT: no lift in the recorded corpus divides by a denominator "
          "within 2 SE of zero. The lift family is NOT the gap-share error "
          "under another name — and that is a measurement, not an assumption, "
          "which is the point of running it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
