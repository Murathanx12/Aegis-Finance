"""G1 correlated-worlds battery (v2) — the declared gate on router capital authority.

ORDER 27 P2 (`docs/ADJUDICATION_2026-08-22_ORDER_27.md`) accepted four
criticisms of the v1 known-answer battery and turned them into a gate:

    "RELIABILITY_ROUTER gains no capital authority beyond v1's aggression knob
     until a correlated-worlds battery (hundreds of worlds, clustered by
     decision date, correlated names, regime blocks) passes at <=5% null
     recommendation AND reports null-world capital exposure."

v1 planted ONE ticker per decision, each name's fate drawn independently. That
world does not exist. In the real ledger a day's decisions share a day: ten
names entered on the same morning rise and fall together, and a router that
prices its standard error off a count of INDEPENDENT observations it does not
have will find edge in a market that only had one opinion. v1's own fix
(`_effective_n`, 2026-08-21) deduplicated the five horizon rows of one
decision; nothing has ever deduplicated the ten names of one day.

What each world here carries that v1's did not:

  clustered decisions   `NAMES_PER_ACTOR_PER_DAY` names decided on the SAME
                        date, not one name per date.
  correlated names      a latent day factor z_d with loading RHO drives every
                        name's outcome that day; the marginal hit rate is held
                        at the world's declared p_hit by construction (the
                        threshold is the exact normal quantile), so the
                        correlation changes the DEPENDENCE and nothing else.
                        A null world is still exactly a null world.
  regime blocks         volatility regime persists in blocks of
                        `REGIME_BLOCK_DAYS` decision days, loads
                        heterogeneously on names by beta, and scales the day
                        factor. The vol_state cells the router conditions on
                        are therefore themselves serially correlated — a
                        HIGH_VOL cell is a few storms, not a random sample.
  multiple actors       three model_ids share the market (the same z_d), so
                        the router is doing what it exists to do — CHOOSING —
                        and the multiplicity of that choice is measured rather
                        than assumed away. `--actors 1` runs the same worlds
                        with the choice removed, which separates "correlation
                        broke it" from "picking the best of three broke it".

Three world types, because a false-positive rate alone can be passed by a
router that never recommends anything:

  null      every actor at p_hit 0.50. Measures the FALSE-POSITIVE rate the
            gate binds, and the capital that rate exposes.
  edge      one actor at EDGE_P, the others null. Measures recovery (that the
            instrument can still see a real edge under correlation) AND
            MISALLOCATION — the weight handed to the two actors that have
            nothing, which is the economic damage a verdict rate cannot show.
  harmful   one actor at HARMFUL_P, the others null. The declared leak is
            ZERO weight, now under correlation.

CAPITAL EXPOSURE is reported because a verdict rate is not what the user pays.
The metric is the share of deployable notional a consumer following the
receipt would place on an actor whose TRUE hit rate is at or below the no-skill
prior — known here by construction, which is the entire point of a planted
world. It is reported three ways (deployed-only, unconditional, and the
NO_EDGE fallback share) because those are three different questions and only
the first is a claim about measurement.

Nothing below is market evidence. Every receipt is stamped
KNOWN_ANSWER_BATTERY, and `backend/services/router_capital_gate.py` refuses to
read a receipt that is not.

Usage:
    python -m scripts.g1_correlated_battery --worlds 300            # audit
    python -m scripts.g1_correlated_battery --worlds 300 --write    # + receipt
    python -m scripts.g1_correlated_battery --worlds 300 --actors 1 --write
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services import router_capital_gate  # noqa: E402
from backend.services.arena import (  # noqa: E402
    experience, store, trust_router)

# ── the declared world (constants are the battery's identity; changing one
#    changes what a passing receipt licensed, so they are hashed into it) ─────
BATTERY_VERSION = "G1_CORRELATED_BATTERY_v2"

N_ACTORS = 3
N_DECISION_DAYS = 16
NAMES_PER_ACTOR_PER_DAY = 8
DECISION_STRIDE = 2          # sessions between decision days
N_SESSIONS = 200             # enough that h=126 matures for the early decisions

#: Loading of every name on its day's latent factor. 0.6 puts ~36% of each
#: outcome's variance in a component the whole day shares — well inside what a
#: single-market long book actually experiences, and the regime blocks push it
#: higher in storms.
RHO = 0.6

REGIME_BLOCK_DAYS = 4        # 16 decision days -> 4 persistent blocks
REGIME_STRESS = (0.0, 1.0)   # calm, stormy multiplier on beta and on |z_d|
STORM_FACTOR_SCALE = 1.6     # stormy days move the common factor harder

NULL_P = 0.50
EDGE_P = 0.62
HARMFUL_P = 0.35

JUMP_UP, JUMP_DOWN = 1.02, 0.98

BOOK_ID = "ENGINE_BASELINE_v1"
BENCHMARK = "SPY"

_NORM = statistics.NormalDist()


# ── price protocol ──────────────────────────────────────────────────────────
class FactorPanel:
    """Computed (not materialised) prices: flat 100 until a name's decision
    session, then gapped +/-2% and held.

    Computed rather than a dict because a world here carries ~400 names x 200
    sessions and this battery builds hundreds of worlds; the dict-of-dicts the
    v1 battery used costs more to allocate than every statistic downstream of
    it. The observable behaviour is identical.
    """

    def __init__(self, sessions: list[date], jumps: dict[str, tuple[int, float]]):
        self._sessions = sessions
        self._index = {s: i for i, s in enumerate(sessions)}
        self._jumps = jumps

    def sessions(self) -> list[date]:
        return list(self._sessions)

    def close_price(self, ticker, day):
        i = self._index.get(day)
        if i is None:
            return None
        j = self._jumps.get(str(ticker).upper())
        if j is None:
            return 100.0 if str(ticker).upper() == BENCHMARK else None
        jump_at, factor = j
        return 100.0 if i <= jump_at else 100.0 * factor

    # open == close: this battery tests the router's inference, not the gap
    # between the forecast and execution legs (that is `experience`'s own
    # tested contract, and pooling the two questions is what reliability.py
    # refuses to do).
    def open_price(self, ticker, day):
        return self.close_price(ticker, day)

    def close_history(self, ticker, day, n):
        i = self._index.get(day)
        if i is None:
            return []
        out = [self.close_price(ticker, s) for s in self._sessions[: i + 1]]
        return [v for v in out if v is not None][-n:]


def _weekdays(n: int, end: date | None = None) -> list[date]:
    end = end or (date.today() - timedelta(days=1))
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


# ── world construction ──────────────────────────────────────────────────────
def _actor_id(a: int) -> str:
    return f"arena_rules@v1#A{a}"


def build_world(root: Path, rng: np.random.Generator, *,
                p_hits: list[float], n_decision_days: int = N_DECISION_DAYS,
                names_per_day: int = NAMES_PER_ACTOR_PER_DAY,
                rho: float = RHO, cluster_adjust: bool | None = None) -> dict:
    """Materialise one correlated world and return the router's live receipt.

    Every layer below the price facts is the production path: real
    `store` files, real `experience.mature_outcomes`, real
    `reliability.decision_cells`, real `trust_router.recommend`.
    """
    decision_idx = [i * DECISION_STRIDE for i in range(n_decision_days)]
    # Derived, never a constant: the panel must outlive the LAST decision by
    # the longest horizon or the late decisions silently never mature, and a
    # world that quietly grades fewer decisions than it planted is a world
    # whose known answer is not the one written down.
    sessions = _weekdays(decision_idx[-1] + max(experience.HORIZONS) + 2)

    # Persistent vol regime: blocks of consecutive decision days, not IID days.
    n_blocks = -(-n_decision_days // REGIME_BLOCK_DAYS)
    block_regime = rng.integers(0, 2, size=n_blocks)

    jumps: dict[str, tuple[int, float]] = {}
    experiences: list[dict] = []
    snapshots: dict[str, dict] = {}

    # Each name carries a persistent base vol and a beta onto regime stress, so
    # a storm re-ranks the cross-section instead of shifting it uniformly (a
    # uniform shift would cancel inside a cross-sectional tercile and the
    # "regime block" would be invisible to the very cells it must perturb).
    for d, si in enumerate(decision_idx):
        day = sessions[si]
        stress = REGIME_STRESS[int(block_regime[d // REGIME_BLOCK_DAYS])]
        # one latent factor for the whole day, across every actor
        z = float(rng.normal()) * (STORM_FACTOR_SCALE if stress else 1.0)
        names_state: dict[str, dict] = {}
        for a, p_hit in enumerate(p_hits):
            thresh = _NORM.inv_cdf(1.0 - p_hit)
            for k in range(names_per_day):
                tkr = f"A{a}D{d:02d}N{k:02d}"
                eps = float(rng.normal())
                latent = rho * z + (1.0 - rho ** 2) ** 0.5 * eps
                hit = latent > thresh
                jumps[tkr] = (si, JUMP_UP if hit else JUMP_DOWN)

                beta = 0.2 + 1.6 * ((k + 1) / (names_per_day + 1))
                base = 0.10 + 0.20 * ((k * 7 + a * 3) % names_per_day) / names_per_day
                vol63 = base * (1.0 + beta * stress) * float(
                    np.exp(0.15 * rng.normal()))
                names_state[tkr] = {"status": "ok", "vol63": round(vol63, 6)}

                experiences.append(experience.make_experience(
                    book_id=BOOK_ID, policy_version=1, ticker=tkr,
                    action="ENTER", decision_date=str(day),
                    information_state_hash=f"W{d:02d}A{a}N{k:02d}",
                    model_id=_actor_id(a), thesis="g1-correlated-battery",
                    rank=None, score=None, chosen_alternative=None))
        snapshots[str(day)] = {"regime_stress": stress, "names": names_state}

    for day, payload in snapshots.items():
        store.freeze_snapshot(day, payload, root)
    store.append_experiences(experiences, root)
    experience.mature_outcomes(FactorPanel(sessions, jumps),
                               benchmark=BENCHMARK, today=sessions[-1],
                               root=root)
    return trust_router.recommend(root=root, leg="forecast",
                                  cluster_adjust=cluster_adjust)


# ── scoring one world ───────────────────────────────────────────────────────
def score_world(rec: dict, p_hits: list[float], *,
                prior: float = trust_router.POPULATION_PRIOR) -> dict:
    """Verdict + capital exposure for one world, against the KNOWN truth.

    `unskilled` is a fact about the world's construction, not an estimate:
    an actor whose true hit rate is at or below the no-skill prior has nothing
    to sell, and every unit of weight it receives is capital the receipt
    misdirected.
    """
    g = rec.get("global") or {}
    verdict = g.get("verdict", "ABSTAIN")
    actors = g.get("actors") or {}
    unskilled = {_actor_id(a) for a, p in enumerate(p_hits) if p <= prior}
    harmful_actors = {_actor_id(a) for a, p in enumerate(p_hits) if p < prior}

    weight_unskilled = sum(float(v.get("weight") or 0.0)
                           for k, v in actors.items() if k in unskilled)
    weight_harmful = sum(float(v.get("weight") or 0.0)
                         for k, v in actors.items() if k in harmful_actors)
    deployed = verdict == "RECOMMENDED"
    return {
        "verdict": verdict,
        # Capital a consumer with authority actually places: v1 deploys on
        # RECOMMENDED. NO_EDGE hands back uniform-by-fallback weights while
        # declaring no measurement, so its share is reported separately and
        # never folded into the deployed number.
        "exposure_deployed": weight_unskilled if deployed else 0.0,
        "exposure_fallback": weight_unskilled if verdict == "NO_EDGE" else 0.0,
        "harmful_weight": weight_harmful if deployed else 0.0,
        "harmful_weight_any_verdict": weight_harmful,
        "n_actors_weighted": sum(1 for v in actors.values()
                                 if float(v.get("weight") or 0.0) > 0.0),
    }


def wilson(k: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    """95% Wilson interval. Quoted with every rate in this battery because
    "0 of 20" bounds the true rate only to ~15% and the count reads as zero
    (ORDER 27 P2: quote the cost rate or do not quote the count)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


# ── the battery ─────────────────────────────────────────────────────────────
def run_arm(tmp_root: Path, *, kind: str, n_worlds: int, n_actors: int,
            seed: int, log_every: int = 25,
            cluster_adjust: bool | None = None,
            n_decision_days: int = N_DECISION_DAYS) -> dict:
    """Run `n_worlds` worlds of one kind and aggregate their scores."""
    p_hits = [NULL_P] * n_actors
    if kind == "edge":
        p_hits[0] = EDGE_P
    elif kind == "harmful":
        p_hits[0] = HARMFUL_P
    elif kind != "null":
        raise ValueError(f"unknown world kind {kind!r}")

    rng = np.random.default_rng(seed)
    scores: list[dict] = []
    t0 = time.time()
    for w in range(n_worlds):
        root = tmp_root / f"{kind}{w:04d}"
        rec = build_world(root, rng, p_hits=p_hits,
                          n_decision_days=n_decision_days,
                          cluster_adjust=cluster_adjust)
        scores.append(score_world(rec, p_hits))
        # Worlds are independent; keeping them costs disk for nothing.
        _rmtree(root)
        if log_every and (w + 1) % log_every == 0:
            print(f"  {kind}: {w + 1}/{n_worlds} worlds "
                  f"({time.time() - t0:.0f}s)", flush=True)

    n_rec = sum(1 for s in scores if s["verdict"] == "RECOMMENDED")
    lo, hi = wilson(n_rec, len(scores))
    verdicts: dict[str, int] = {}
    for s in scores:
        verdicts[s["verdict"]] = verdicts.get(s["verdict"], 0) + 1
    return {
        "kind": kind,
        "p_hits": p_hits,
        "n_worlds": len(scores),
        "n_recommended": n_rec,
        "recommendation_rate": round(n_rec / len(scores), 4) if scores else None,
        "recommendation_rate_ci95": [round(lo, 4), round(hi, 4)],
        "verdicts": verdicts,
        "mean_exposure_deployed": round(
            _mean([s["exposure_deployed"] for s in scores]), 4),
        "mean_exposure_given_deployed": round(
            _mean([s["exposure_deployed"] for s in scores
                   if s["verdict"] == "RECOMMENDED"]), 4),
        "mean_exposure_fallback": round(
            _mean([s["exposure_fallback"] for s in scores]), 4),
        "n_worlds_leaking_harmful_weight": sum(
            1 for s in scores if s["harmful_weight_any_verdict"] > 0.0),
        "max_harmful_weight": round(
            max([s["harmful_weight_any_verdict"] for s in scores] or [0.0]), 4),
        "elapsed_s": round(time.time() - t0, 1),
    }


def _rmtree(p: Path) -> None:
    import shutil
    shutil.rmtree(p, ignore_errors=True)


def router_fingerprint(cluster_adjust: bool) -> dict:
    """What a passing receipt licenses: THIS router, at THESE parameters.

    Computed by the GATE, not here, so the receipt is stamped with the same
    function the gate later compares against. Two implementations of "which
    router was this" is one implementation too many — they would drift, and
    the drift would show up as a licence nobody granted.
    """
    return router_capital_gate.live_router_fingerprint(cluster_adjust)


def battery_fingerprint(n_actors: int,
                        n_decision_days: int = N_DECISION_DAYS) -> dict:
    """The WORLD's identity. A gate that accepted any battery receipt would
    accept one run at rho=0 — which is the v1 world the gate exists to
    replace."""
    return {
        "battery_version": BATTERY_VERSION,
        "n_actors": n_actors,
        "n_decision_days": n_decision_days,
        "names_per_actor_per_day": NAMES_PER_ACTOR_PER_DAY,
        "rho": RHO,
        "regime_block_days": REGIME_BLOCK_DAYS,
        "storm_factor_scale": STORM_FACTOR_SCALE,
        "null_p": NULL_P, "edge_p": EDGE_P, "harmful_p": HARMFUL_P,
    }


def run_battery(tmp_root: Path, *, n_null: int, n_edge: int, n_harmful: int,
                n_actors: int = N_ACTORS, seed: int = 20260823,
                log_every: int = 25, cluster_adjust: bool | None = None,
                n_decision_days: int = N_DECISION_DAYS) -> dict:
    from datetime import datetime, timezone

    if cluster_adjust is None:
        cluster_adjust = trust_router.CLUSTER_ADJUST_DEFAULT
    arms = {}
    for i, (kind, n) in enumerate((("null", n_null), ("edge", n_edge),
                                   ("harmful", n_harmful))):
        if n <= 0:
            continue
        arms[kind] = run_arm(tmp_root, kind=kind, n_worlds=n,
                             n_actors=n_actors, seed=seed + 1000 * i,
                             log_every=log_every, cluster_adjust=cluster_adjust,
                             n_decision_days=n_decision_days)

    null, edge, harm = arms.get("null"), arms.get("edge"), arms.get("harmful")
    return {
        "mode": "KNOWN_ANSWER_BATTERY",
        "gate": "ROUTER_CAPITAL_AUTHORITY",
        "battery": battery_fingerprint(n_actors, n_decision_days),
        "router": router_fingerprint(cluster_adjust),
        "seed": seed,
        "arms": arms,
        # The fields the gate binds, hoisted so a reader never has to know
        # which arm carries which number.
        "n_null_worlds": null["n_worlds"] if null else 0,
        "null_recommendation_rate": null["recommendation_rate"] if null else None,
        "null_recommendation_rate_ci95": (null["recommendation_rate_ci95"]
                                          if null else None),
        "null_capital_exposure_deployed": (null["mean_exposure_deployed"]
                                           if null else None),
        "null_capital_exposure_given_deployed": (
            null["mean_exposure_given_deployed"] if null else None),
        "null_capital_exposure_fallback": (null["mean_exposure_fallback"]
                                           if null else None),
        "edge_recovery_rate": edge["recommendation_rate"] if edge else None,
        "edge_misallocated_weight_given_deployed": (
            edge["mean_exposure_given_deployed"] if edge else None),
        "harmful_leak_worlds": (harm["n_worlds_leaking_harmful_weight"]
                                if harm else None),
        "harmful_max_weight": harm["max_harmful_weight"] if harm else None,
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": ("SENSITIVITY/KNOWN-ANSWER artifact — synthetic worlds with a "
                 "planted truth. Nothing here is market evidence and no return "
                 "claim may cite it."),
    }


RECEIPT_PATH = (Path(__file__).resolve().parents[1] / "backend" / "data" /
                "optimus" / "g1_correlated_battery.json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--worlds", type=int, default=300,
                    help="null worlds (the arm the <=5%% bar binds)")
    ap.add_argument("--edge-worlds", type=int, default=60)
    ap.add_argument("--harmful-worlds", type=int, default=60)
    ap.add_argument("--actors", type=int, default=N_ACTORS)
    ap.add_argument("--decision-days", type=int, default=N_DECISION_DAYS,
                    help="clustered decision days per world (the axis that "
                         "buys independent information once names within a "
                         "day no longer do)")
    ap.add_argument("--cluster-adjust", dest="cluster_adjust",
                    action="store_true", default=None,
                    help="measure the router with decision-date design-effect "
                         "correction ON (default: the module's declared "
                         "CLUSTER_ADJUST_DEFAULT)")
    ap.add_argument("--no-cluster-adjust", dest="cluster_adjust",
                    action="store_false")
    ap.add_argument("--seed", type=int, default=20260823)
    ap.add_argument("--write", action="store_true",
                    help="write the receipt the capital gate reads")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import tempfile
    with tempfile.TemporaryDirectory(prefix="g1battery_") as td:
        out = run_battery(Path(td), n_null=args.worlds, n_edge=args.edge_worlds,
                          n_harmful=args.harmful_worlds, n_actors=args.actors,
                          seed=args.seed, cluster_adjust=args.cluster_adjust,
                          n_decision_days=args.decision_days)

    print(json.dumps({k: v for k, v in out.items() if k != "arms"}, indent=2))
    for arm in out["arms"].values():
        print(json.dumps(arm, indent=2))

    if args.write:
        path = Path(args.out) if args.out else RECEIPT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nreceipt -> {path}")
    else:
        print("\n(audit only — pass --write to persist the receipt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
