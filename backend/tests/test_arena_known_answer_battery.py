"""G1 known-answer battery: plant a KNOWN world, demand the KNOWN answer.

The G1 flip condition (roadmap) is a DECLARED false-positive rate and a
DECLARED false-kill rate for the grades→trust chain, measured end-to-end:
synthetic experiences → real `experience.mature_outcomes` over a constructed
price panel → real `reliability.decision_cells` → real
`trust_router.recommend`. Nothing is mocked below the test's own price facts.

Declared rates (fixed seeds make every number below deterministic):

  false-positive   ≤ 12.5% of null worlds (true hit rate 0.50) may reach a
                   global RECOMMENDED. The router's bar is EDGE_Z·SE ≈ one-
                   sided 6.7% per actor; the multiplicity across horizon
                   cells is what this battery measures rather than assumes.
  false-kill       ≤ 30% at the declared effect (true hit rate 0.65,
                   ~100 decisions): recovery power ≥ 70%. A subtler edge
                   than 0.65 is DECLARED UNDETECTABLE at this n — that is a
                   statement of the design's floor, not a defect.
  harmful leak     0 of 20 harmful worlds (true hit rate 0.35) may assign
                   the harmful actor a positive weight.

Worlds are built one ticker per decision: a hit gaps +2% the session after
the decision and stays; a miss gaps −2%. SPY stays flat. The sign is
therefore identical at every horizon, so each horizon cell receives the same
planted rate — the known answer.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from backend.services.arena import experience, store, trust_router


class DictPanel:
    def __init__(self, sessions, closes: dict):
        self._sessions = list(sessions)
        self._closes = closes

    def sessions(self):
        return list(self._sessions)

    def close_price(self, ticker, day):
        return self._closes.get(ticker.upper(), {}).get(day)

    def open_price(self, ticker, day):
        return self.close_price(ticker, day)

    def close_history(self, ticker, day, n):
        px = self._closes.get(ticker.upper(), {})
        return [px[s] for s in self._sessions if s <= day and s in px][-n:]


def _weekdays(n, end=None):
    end = end or (date.today() - timedelta(days=1))
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


N_DECISIONS = 100
N_SESSIONS = 130  # decisions on the first 100 sessions; h=63 still matures
                  # for the early ones, h=126 for none — as in production,
                  # cells report whatever n they truly have


def _world(root, rng: np.random.Generator, p_hit: float) -> str:
    """Build one synthetic world and return the router's global verdict."""
    ss = _weekdays(N_SESSIONS)
    closes = {"SPY": {s: 100.0 for s in ss}}
    recs = []
    for i in range(N_DECISIONS):
        t = f"T{i:03d}"
        hit = bool(rng.random() < p_hit)
        jump = 1.02 if hit else 0.98
        closes[t] = {s: (100.0 if j <= i else 100.0 * jump)
                     for j, s in enumerate(ss)}
        recs.append(experience.make_experience(
            book_id="ENGINE_BASELINE_v1", policy_version=1, ticker=t,
            action="ENTER", decision_date=str(ss[i]),
            information_state_hash=f"H{i}", model_id="arena_rules@v1",
            thesis="battery", rank=None, score=None,
            chosen_alternative=None))
    store.append_experiences(recs, root)
    experience.mature_outcomes(DictPanel(ss, closes), today=ss[-1], root=root)
    rec = trust_router.recommend(root=root, leg="forecast")
    return rec


def _verdict(rec: dict) -> str:
    return (rec.get("global") or {}).get("verdict", "ABSTAIN")


def _actor_weight(rec: dict) -> float:
    weights = (rec.get("global") or {}).get("weights") or {}
    return float(weights.get("arena_rules@v1", 0.0))


class TestKnownAnswerBattery:
    def test_null_worlds_false_positive_rate_stays_under_declared(
            self, tmp_path):
        """40 worlds with NOTHING to find: RECOMMENDED ≤ 12.5% of them."""
        rng = np.random.default_rng(11)
        hits = 0
        for r in range(40):
            root = tmp_path / f"null{r}"
            if _verdict(_world(root, rng, p_hit=0.50)) == "RECOMMENDED":
                hits += 1
        assert hits <= 5, (
            f"false-positive rate {hits}/40 exceeds the declared 12.5% — "
            f"the router is finding edge in coin flips")

    def test_planted_edge_is_recovered_at_declared_power(self, tmp_path):
        """20 worlds with a true 0.65 hit rate: RECOMMENDED ≥ 70% of them
        (false-kill ≤ 30% at the declared effect)."""
        rng = np.random.default_rng(22)
        found = 0
        for r in range(20):
            root = tmp_path / f"edge{r}"
            if _verdict(_world(root, rng, p_hit=0.65)) == "RECOMMENDED":
                found += 1
        assert found >= 14, (
            f"recovery {found}/20 under the declared 70% power — a real "
            f"0.65-hit model is being killed as noise (false-kill "
            f"{20 - found}/20 > 30%)")

    def test_harmful_actor_never_earns_weight(self, tmp_path):
        """20 worlds with a truly harmful model (0.35): weight 0.0, always.

        The declared harmful-leak rate is ZERO — not a percentage. A capital
        router that sometimes trusts a measurably harmful model has no floor
        worth the name.
        """
        rng = np.random.default_rng(33)
        for r in range(20):
            root = tmp_path / f"harm{r}"
            rec = _world(root, rng, p_hit=0.35)
            assert _verdict(rec) != "RECOMMENDED"
            assert _actor_weight(rec) == 0.0, (
                f"world {r}: harmful actor earned weight "
                f"{_actor_weight(rec)}")

    def test_the_battery_is_deterministic(self, tmp_path):
        """Same seed, same world, same verdict — twice. Without this, a
        battery failure could never be reproduced to be diagnosed."""
        a = _world(tmp_path / "a", np.random.default_rng(7), p_hit=0.65)
        b = _world(tmp_path / "b", np.random.default_rng(7), p_hit=0.65)
        assert _verdict(a) == _verdict(b)
        assert (a.get("global") or {}).get("weights") == \
            (b.get("global") or {}).get("weights")
