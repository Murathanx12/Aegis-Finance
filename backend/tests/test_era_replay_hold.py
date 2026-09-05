"""C4 -- the HOLD arm of the era replay, and the second era's build lock.

WHAT THESE TESTS ARE FOR
========================
Three things could make the 2026-09-06b hold receipt a lie, and each has a test
here rather than a promise in a docstring:

1. **The rule could not be the rule.** `scripts/era_replay_v2.select_with_hold`
   is a re-implementation of `learner/evaluate.py::book`'s `hold_k` hysteresis,
   because the era-replay grader is bespoke (8-name bundles with a sealed
   forward column, not a monthly panel). Two implementations of one rule is two
   rules unless something checks, so `test_agrees_with_learner_evaluate_book`
   runs both over the same synthetic panel and compares month by month.

2. **The band could not be a band.** `hold_n == top_n` is the no-hysteresis
   rule written a longer way. It must reproduce the plain top-k selection
   exactly (so the equivalence is provable) and `grade_arm` must REFUSE it (so
   no receipt reports a band where there is none) -- the same asymmetry
   `evaluate.book` already enforces.

3. **The second era could reach the wire.** Part (b) of the mandate builds
   2010-2013 windows and is forbidden to pay for their decide step. That is
   enforced on the DATA in `assert_decidable`, immediately before every vendor
   call, and by a CLI refusal on top. Both are tested, because a lock that is
   only a flag is a lock anybody can talk their way past.

Everything here is OFFLINE. No test in this file loads the long panel, calls a
provider, or writes into `continuation_2026-09-06/`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]

from scripts import era_replay_v2 as E                          # noqa: E402
from scripts import c6b_era_replay_hold as C4                   # noqa: E402


# ── 1. the selector ────────────────────────────────────────────────────────

def test_hold_n_equal_to_top_n_reproduces_the_no_hold_book():
    """`hold_n == top_n` is the no-hysteresis rule written a longer way."""
    rng = np.random.default_rng(20260906)
    for _ in range(200):
        k = 8
        ranks = rng.permutation(k).astype(float)
        permnos = list(range(100, 100 + k))
        prev = set(rng.choice(permnos, size=int(rng.integers(0, k + 1)),
                              replace=False).tolist())
        plain = E.select_with_hold(ranks, permnos, prev, 3, None)
        degen = E.select_with_hold(ranks, permnos, prev, 3, 3)
        assert sorted(plain) == sorted(degen)
        assert sorted(plain) == sorted(i for i in range(k) if ranks[i] < 3)


def test_hold_keeps_an_incumbent_that_slipped_inside_the_band():
    ranks = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    permnos = [10, 11, 12, 13, 14, 15, 16, 17]
    # 13 sits at rank position 3 -- outside the buy rank (3), inside the band (6)
    plain = E.select_with_hold(ranks, permnos, set(), 3, None)
    held = E.select_with_hold(ranks, permnos, {13}, 3, 6)
    assert sorted(plain) == [0, 1, 2]
    assert 3 in held and len(held) == 3
    # the incumbent displaces the WORST of the would-be top-3, never the best
    assert 0 in held and 1 in held


def test_hold_does_not_keep_an_incumbent_outside_the_band():
    ranks = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    permnos = [10, 11, 12, 13, 14, 15, 16, 17]
    held = E.select_with_hold(ranks, permnos, {17}, 3, 6)   # rank 7 > hold 6
    assert sorted(held) == [0, 1, 2]


def test_hold_lowers_turnover_on_a_synthetic_ranking():
    """The point of the rule: the same ranking, fewer round trips."""
    rng = np.random.default_rng(7)
    permnos = list(range(100, 108))
    top_n, hold_n = 3, 6
    turn = {}
    for label, hn in (("nohold", None), ("hold", hold_n)):
        prev: set[int] = set()
        acc = []
        for m in range(24):
            # a stable-ish ranking with jitter: names drift in and out of the
            # top 3 but rarely leave the top 6. That is exactly the situation
            # hysteresis exists for.
            base = np.arange(8, dtype=float)
            ranks = np.argsort(np.argsort(base + rng.normal(0, 1.2, 8))).astype(float)
            pick = E.select_with_hold(ranks, permnos, prev, top_n, hn)
            cur = {permnos[i] for i in pick}
            acc.append(1.0 if not prev else len(cur - prev) / len(cur))
            prev = cur
        turn[label] = float(np.mean(acc))
    assert turn["hold"] < turn["nohold"], turn


def test_agrees_with_learner_evaluate_book_on_a_synthetic_panel():
    """The bespoke selector and `learner.evaluate.book` are the SAME rule."""
    from learner import evaluate

    rng = np.random.default_rng(11)
    months = [f"2020-{m:02d}" for m in range(1, 13)]
    permnos = list(range(500, 512))                      # 12 names
    k, hold_k = 3, 6
    rows = []
    preds: dict[str, dict[int, float]] = {}
    rets: dict[str, dict[int, float]] = {}
    for m in months:
        # distinct predictions -> no tie-break ambiguity between the two paths
        p = rng.permutation(len(permnos)).astype(float) + rng.normal(0, .01, len(permnos))
        r = rng.normal(0.01, 0.05, len(permnos))
        preds[m] = dict(zip(permnos, p))
        rets[m] = dict(zip(permnos, r))
        for pn in permnos:
            rows.append({"month": m, "permno": pn, "pred": preds[m][pn],
                         "fwd_1m": rets[m][pn], "mkt_vw_1m": 0.004,
                         "market_cap": 1000.0})
    df = pd.DataFrame(rows)

    got = evaluate.book(df, "pred", k=k, weight="ew", cost_bps=10.0,
                        hold_k=hold_k, return_series=True)
    assert got["hold_k"] == hold_k

    prev: set[int] = set()
    mine_ret, mine_turn = [], []
    for m in months:
        order = sorted(permnos, key=lambda pn: -preds[m][pn])
        rank_pos = {pn: i for i, pn in enumerate(order)}
        ranks = np.array([rank_pos[pn] for pn in permnos], dtype=float)
        pick = E.select_with_hold(ranks, permnos, prev, k, hold_k)
        cur = {permnos[i] for i in pick}
        mine_ret.append(float(np.mean([rets[m][pn] for pn in cur])))
        mine_turn.append(1.0 if not prev else len(cur - prev) / len(cur))
        prev = cur

    ref_gross = got["_series"]["gross"].to_numpy()
    ref_turn = got["_series"]["turnover"].to_numpy()
    assert np.allclose(ref_gross, np.array(mine_ret), atol=1e-12)
    assert np.allclose(ref_turn, np.array(mine_turn), atol=1e-12)


def test_grade_arm_refuses_a_band_that_is_not_a_band():
    with pytest.raises(SystemExit) as ei:
        E.grade_arm([], {}, "fantasy_nodiary", 10.0, hold_n=E.TOP_N)
    assert "REFUSED" in str(ei.value)


# ── 2. the second era cannot reach the wire ────────────────────────────────

def test_assert_decidable_allows_the_frozen_era():
    E.assert_decidable({"window_id": "t0_2016-01", "month": "2016-01"})
    E.assert_decidable({"window_id": "t3_2019-12"})          # month parsed out


@pytest.mark.parametrize("month", ["2010-01", "2012-07", "2013-12", "2020-05"])
def test_assert_decidable_refuses_anything_outside_it(month):
    with pytest.raises(E.DecideOutsideFrozenEra):
        E.assert_decidable({"window_id": f"t0_{month}", "month": month})


def test_assert_decidable_refuses_when_the_era_cannot_be_derived():
    """A guard DERIVES its inputs or REFUSES -- it never defaults to allow."""
    with pytest.raises(E.DecideOutsideFrozenEra):
        E.assert_decidable({"window_id": "t0_unknown"})


def test_cli_refuses_to_decide_a_second_era():
    for extra in (["--run"], ["--pilot", "5"]):
        with pytest.raises(SystemExit) as ei:
            E.main(["--era", "2010-2013", *extra])
        assert "REFUSED" in str(ei.value)


def test_the_wire_is_locked_before_the_gate_is_even_consulted(monkeypatch):
    """`assert_decidable` fires ahead of `_gate`, so no budget call is needed
    to stop a second-era decide -- and a CACHE HIT is unaffected."""
    def boom(*_a, **_k):                                       # pragma: no cover
        raise AssertionError("_gate must not be reached for a locked era")
    monkeypatch.setattr(E, "_gate", boom)
    with pytest.raises(E.DecideOutsideFrozenEra):
        E.call_decider({}, ["Company A"], None, None,
                       {"window_id": "t0_2011-03", "month": "2011-03",
                        "arm": "fantasy_nodiary"})


# ── 3. the receipts ────────────────────────────────────────────────────────

RECEIPTS_B = REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06b"


@pytest.mark.parametrize("name", ["C4_era_replay_hold_run01.json",
                                  "C4b_era2_window_build_dryrun.json"])
def test_receipt_carries_provenance_with_non_empty_inputs_opened(name):
    p = RECEIPTS_B / name
    if not p.exists():
        pytest.skip(f"{name} not written on this machine")
    rec = json.loads(p.read_text(encoding="utf-8"))
    prov = rec.get("_provenance")
    assert isinstance(prov, dict), "receipt has no _provenance block"
    for key in ("sys_argv", "resolved_config", "_inputs_opened", "git_commit",
                "generated_utc"):
        assert key in prov, f"_provenance missing {key}"
    opened = prov["_inputs_opened"]
    assert isinstance(opened, list) and opened, "_inputs_opened is empty"
    hashed = [o for o in opened if o.get("sha256")]
    assert hashed, "_inputs_opened records no hashed input"
    for o in hashed:
        assert Path(o["path"]).is_absolute(), o["path"]
        assert len(o["sha256"]) == 64
        assert o["bytes"] > 0
    assert rec.get("llm_spend_usd") == 0.0
    assert rec.get("llm_calls_made") == 0


def test_hold_receipt_reproduces_the_sealed_no_hold_numbers():
    """The free re-grade is the SAME experiment, or the hold cells mean nothing."""
    p = RECEIPTS_B / "C4_era_replay_hold_run01.json"
    if not p.exists():
        pytest.skip("hold receipt not written on this machine")
    rec = json.loads(p.read_text(encoding="utf-8"))
    repro = rec["no_hold_reproduction_check"]
    for arm in E.ARMS:
        assert repro[arm] == "IDENTICAL", (arm, repro[arm])
    assert rec["cache_coverage"]["wire_calls_made"] == 0
    assert rec["family_size_8"]["family_size"] == 8


def test_hold_declaration_hash_matches_the_module():
    p = C4.DECLARATION
    if not p.exists():
        pytest.skip("declaration not written on this machine")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["hold_rule_sha256"] == C4.rule_sha()
    assert d["hold_rule"]["hold_k"] == 2 * E.TOP_N
    assert d["llm_calls_authorised"] == 0


def test_era2_receipt_says_cannot_build_and_names_why():
    p = RECEIPTS_B / "C4b_era2_window_build_dryrun.json"
    if not p.exists():
        pytest.skip("era-2 receipt not written on this machine")
    rec = json.loads(p.read_text(encoding="utf-8"))
    assert rec["decide_step"]["run_this_session"] is False
    assert rec["decide_step"]["llm_calls_made_by_this_job"] == 0
    # the two clocks are two fields, not one shared bound
    b = rec["edgar_backing"]
    assert b["pit_backward_bound"] != b["pit_forward_window"]
    assert "acceptance_datetime" in b["pit_backward_bound"]


# ── 4. the replay is free ──────────────────────────────────────────────────

def test_replay_from_cache_never_touches_the_wire(monkeypatch):
    if not (E.WINDOWS_PATH.exists() and E.CACHE_PATH.exists()):
        pytest.skip("era-replay windows/cache not on this machine")

    def boom(*_a, **_k):                                       # pragma: no cover
        raise AssertionError("replay_from_cache put something on the wire")
    monkeypatch.setattr(E, "_gate", boom)
    monkeypatch.setattr(E, "_nano_client", boom)
    monkeypatch.setattr(E, "_ds_client", boom)

    wrec = E.load_windows()
    wins = wrec["windows"][:8]
    E._load_cache()
    res = E.replay_from_cache(wins, E.ARMS)
    assert res["coverage"]["wire_calls_made"] == 0
    assert res["coverage"]["usd_spent"] == 0.0
    assert res["coverage"]["decisions_wanted"] == len(wins) * len(E.ARMS)
