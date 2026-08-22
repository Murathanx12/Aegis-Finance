"""Does the G1 battery's world contain the answer the battery says it does?

The battery measures a router against a planted truth. If the planting is
wrong, every number it produces is a correct calculation against the wrong
world — the house failure mode, and one that no amount of care in the router
would catch. So the world itself is tested here, on its three declared
properties:

  the null world is NULL          marginal hit rate 0.50, not "about a half"
  the names are CORRELATED        within-day variance inflation well above 1,
                                  or this is the v1 world it exists to replace
  the regime blocks REACH the
  cells the router conditions on  all three vol_state terciles populated

The full battery is a script, not a test: hundreds of worlds is a minutes-long
run whose output is a committed receipt (`scripts/g1_correlated_battery.py`,
read by `backend/services/router_capital_gate.py`). What lives here is the
part that must not be allowed to rot silently between runs.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.arena import reliability, store
from scripts.g1_correlated_battery import NULL_P, build_world

N_WORLDS = 6
SEED = 4242


@pytest.fixture(scope="module")
def worlds(tmp_path_factory):
    """Build a few null worlds once and read back what was actually planted."""
    root = tmp_path_factory.mktemp("g1world")
    rng = np.random.default_rng(SEED)
    hits: list[int] = []
    day_rates: list[float] = []
    names_per_day: list[int] = []
    vol_states: dict[str, int] = {}
    for w in range(N_WORLDS):
        r = root / f"w{w}"
        build_world(r, rng, p_hits=[NULL_P] * 3)
        by_day: dict[str, list[int]] = {}
        for o in store.read_outcomes(r):
            # ONE row per decision: the five horizon rows of one decision are
            # one decision, and counting them all would fake the sample size
            # the battery exists to stop the router faking.
            if o["horizon_days"] != 21:
                continue
            hit = 1 if o["outcome_class"] in ("GOOD_CALL", "GOOD_PASS") else 0
            hits.append(hit)
            by_day.setdefault(o["decision_date"], []).append(hit)
        for day_hits in by_day.values():
            day_rates.append(sum(day_hits) / len(day_hits))
            names_per_day.append(len(day_hits))
        rep = reliability.decision_cells(
            root=r, by=("model_id", "horizon_days", "vol_state"))
        for c in rep["cells"].values():
            vol_states[c["vol_state"]] = vol_states.get(c["vol_state"], 0) + 1
    return {"hits": np.array(hits), "day_rates": np.array(day_rates),
            "m": float(np.mean(names_per_day)), "vol_states": vol_states}


def test_the_null_world_is_actually_null(worlds):
    """The planted marginal rate is exactly 0.50 by construction (the hit
    threshold is the normal quantile of p_hit), so the realised rate may only
    miss it by sampling error — and the sampling error that applies is the
    CLUSTERED one, which is ~3x the naive binomial figure."""
    h = worlds["hits"]
    p = h.mean()
    naive_se = (0.25 / len(h)) ** 0.5
    # generous: 4 clustered standard errors, with the inflation measured below
    assert abs(p - 0.50) < 4 * naive_se * 3.0, (
        f"planted null world realised a {p:.4f} hit rate over {len(h)} "
        f"decisions — the battery's 'known answer' is not the one written "
        f"down, and every number measured against it is wrong")


def test_the_names_within_a_day_move_together(worlds):
    """Variance inflation is the whole point of this battery. At VIF ~= 1 the
    world is v1's — independent names — and a router tuned against it would be
    licensed for a market that does not exist."""
    dr, m = worlds["day_rates"], worlds["m"]
    observed_sd = dr.std()
    independent_sd = 0.5 / (m ** 0.5)
    vif = (observed_sd / independent_sd) ** 2
    assert vif > 2.0, (
        f"within-day variance inflation {vif:.2f} — the names are not moving "
        f"together, so this is the independent world the gate replaced")


def test_the_regime_blocks_reach_the_routers_cells(worlds):
    """The router conditions on vol_state terciles. If the regime never
    re-ranks the cross-section, those cells are a name attribute rather than a
    state and the 'regime blocks' in the design are decorative."""
    seen = worlds["vol_states"]
    for state in ("LOW_VOL", "MID_VOL", "HIGH_VOL"):
        assert seen.get(state, 0) > 0, f"no {state} cells: {seen}"
    assert seen.get("UNKNOWN_VOL", 0) == 0, (
        "unlabelled days mean the frozen snapshots were too thin to tercile")


def test_the_world_is_deterministic(tmp_path):
    """A battery failure that cannot be reproduced cannot be diagnosed."""
    a = build_world(tmp_path / "a", np.random.default_rng(7),
                    p_hits=[NULL_P] * 3)
    b = build_world(tmp_path / "b", np.random.default_rng(7),
                    p_hits=[NULL_P] * 3)
    assert a["global"]["verdict"] == b["global"]["verdict"]
    assert a["global"]["actors"] == b["global"]["actors"]
