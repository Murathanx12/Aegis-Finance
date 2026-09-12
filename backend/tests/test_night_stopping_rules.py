"""E5's five known-answer tests: does the stopping rule DISCRIMINATE?

A gate that refuses everything is not strict, it is broken, and a gate that
passes everything is decoration. These tests plant a known answer on both
sides -- 200 null lineages whose maximum must NOT survive the deflation, and
one genuinely elevated lineage among the same 200 that must -- so the wiring
is checked rather than the vendored arithmetic, which has its own tests
upstream.

Offline, no network, no night directory: every fixture is synthesized and
every write goes to `tmp_path`.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from scripts import night_stopping_rules as E5

SEED = 20260912


# ------------------------------------------------------------ fixtures

def _eval_row(key, lineage, bank, fitness, *, gen=0, n_windows=24):
    return {"key": key, "lineage": lineage, "parents": [], "bank_seed": bank,
            "gen": gen, "genome": {"k": 50}, "full_dev_max_dd": -0.2,
            "result": {"verdict": "OK", "n_windows": n_windows,
                       "fitness": float(fitness)},
            "utc": "2026-09-12T00:00:00+00:00"}


def _cohort(n_lineages=200, n_banks=60, *, planted_mean=None, seed=SEED):
    """`n_lineages` lineages, each one genome measured on `n_banks` banks.

    Every lineage is drawn from the SAME null (mean 0) except, when
    `planted_mean` is given, lineage `real` whose per-bank excess is shifted.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_lineages):
        key = f"g{i:04d}"
        draws = rng.normal(0.0, 5.0, size=n_banks)
        for b, f in enumerate(draws):
            rows.append(_eval_row(key, key, 100000 + b, f))
    if planted_mean is not None:
        draws = rng.normal(planted_mean, 5.0, size=n_banks)
        for b, f in enumerate(draws):
            rows.append(_eval_row("real", "real", 100000 + b, f))
    return rows


# ------------------------------------------------- 1. the noise lineage fails

def test_a_planted_pure_noise_lineage_does_not_survive_the_deflation():
    """200 lineages from one null: the BEST of them clears t>0 and must not
    clear DSR. This is `multipletesting.py`'s own worked example re-run through
    E5's wrapper -- what is under test is the wiring, not the arithmetic."""
    # n_splits=4 rather than 16: CSCV over 200 columns is 12,870 subset
    # combinations and this test is about the DEFLATION, not about PBO.
    res = E5.stopping_verdicts(_cohort(), min_banks=2, n_splits=4)
    assert res["n_trials_effective_proxy"] == 200
    assert res["n_lineages_admitted"] == 200
    best = max(res["verdicts"], key=lambda v: v["fitness_median"])
    assert best["observed_sharpe"] > 0, "the best of 200 nulls should look good"
    assert best["dsr_status"] == "ok"
    assert best["dsr_survives"] is False
    assert best["verdict"] == "DEPRIORITIZED"
    assert "DSR" in best["reason"]
    survivors = [v for v in res["verdicts"] if v["dsr_survives"]]
    assert not survivors, f"{len(survivors)} pure-noise lineages survived"


# --------------------------------------------------- 2. the real edge survives

def test_a_planted_real_edge_survives_the_same_bar_that_killed_the_nulls():
    """The discrimination test. Same 200 nulls, same n_trials, one lineage with
    a genuinely elevated mean: it must survive where every null failed, or the
    gate is merely strict."""
    res = E5.stopping_verdicts(_cohort(planted_mean=6.0), min_banks=2, n_splits=4)
    rows = {v["lineage"]: v for v in res["verdicts"]}
    assert rows["real"]["dsr_status"] == "ok"
    assert rows["real"]["dsr_survives"] is True
    assert rows["real"]["verdict"] in ("ACTIVE", "DEPRIORITIZED")
    # every OTHER lineage is still a null and still fails
    others = [v for k, v in rows.items() if k != "real"]
    assert not [v for v in others if v["dsr_survives"]]


# ------------------------------------------------------------- 3. PBO fires

def test_PBO_deprioritizes_a_known_overfit_matrix_even_when_DSR_would_pass():
    """The two gates are not redundant. A matrix whose in-sample winner ranks
    randomly out-of-sample must produce pbo > 0.5 and take the PBO branch."""
    rng = np.random.default_rng(7)
    n_banks, n_strats = 320, 8
    rows = []
    for s in range(n_strats):
        # pure noise, so in-sample selection carries nothing out of sample
        draws = rng.normal(0.0, 1.0, size=n_banks)
        for b, f in enumerate(draws):
            rows.append(_eval_row(f"s{s}", f"s{s}", 900000 + b, f))
    res = E5.stopping_verdicts(rows, min_banks=2)
    assert res["pbo"]["pbo_status"] == "ok", res["pbo"]
    assert res["pbo"]["pbo"] > 0.5, res["pbo"]
    assert all(v["verdict"] == "DEPRIORITIZED" for v in res["verdicts"])
    # and the PBO branch is reachable on its own: a row whose DSR passed still
    # gets DEPRIORITIZED when PBO is over the bar
    passing_dsr = {"dsr_status": "ok", "dsr_survives": True, "dsr": 0.99,
                   "dsr_bar": 0.95, "n_trials": 8}
    verdict, reason = E5.verdict_for(passing_dsr, res["pbo"])
    assert verdict == "DEPRIORITIZED" and reason.startswith("PBO")


# ------------------------------------------- 4. the two trial counts differ

def test_n_trials_raw_and_the_lineage_proxy_move_the_bar_in_the_right_direction():
    """500 genomes in 12 lineages: raw 500, proxy 12, and the raw count is the
    HARDER bar because the expected maximum of N draws grows with N."""
    rng = np.random.default_rng(11)
    rows = []
    for lin in range(12):
        for member in range(42):          # 12 * 42 = 504 distinct genomes
            key = f"L{lin}_m{member}"
            n_banks = 40 if member == 0 else 2
            for b in range(n_banks):
                rows.append(_eval_row(key, f"L{lin}", 700000 + b,
                                      rng.normal(1.0, 4.0)))
    built = E5.lineage_table(rows, min_banks=2)
    assert built["n_trials_raw"] == 504
    assert built["n_trials_effective_proxy"] == 12
    vec = list(built["table"]["L0"]["fitness_vector"])
    hard = E5.dsr_row(vec, n_trials=504, trial_sharpe_std=1.0)
    easy = E5.dsr_row(vec, n_trials=12, trial_sharpe_std=1.0)
    assert hard["expected_maximum_sharpe"] > easy["expected_maximum_sharpe"]
    assert hard["dsr"] <= easy["dsr"]


# --------------------------------- 5. an unrunnable PBO never crashes the job

def test_PBO_insufficient_windows_is_a_status_and_not_an_exception():
    """Six measured banks cannot be split 16 ways. The job must keep going and
    say so -- `a check that did not run is not a check that passed`."""
    rows = []
    for s in range(3):
        for b in range(6):
            rows.append(_eval_row(f"t{s}", f"t{s}", 500000 + b, 1.0 + 0.1 * b))
    res = E5.stopping_verdicts(rows, min_banks=2)
    assert res["pbo"]["pbo_status"] == "insufficient_windows"
    assert res["pbo"]["pbo"] is None
    assert {v["verdict"] for v in res["verdicts"]} == {"CANNOT_DETERMINE"}
    assert all(v["dsr_status"] == "insufficient_observations"
               for v in res["verdicts"])


# ------------------------------------------------- the refusals say WHY

def test_a_thin_lineage_is_a_refusal_and_not_a_failed_test():
    """The distinction with consequences: `insufficient_observations` must not
    read as DEPRIORITIZED, because the two say opposite things about whether
    the next night should keep breeding from the lineage."""
    row = E5.dsr_row([1.0, 2.0, 3.0], n_trials=100, trial_sharpe_std=1.0)
    assert row["dsr_status"] == "insufficient_observations"
    assert row["dsr"] is None and row["dsr_survives"] is None
    assert str(E5.MIN_DSR_OBSERVATIONS) in row["reason"]
    verdict, reason = E5.verdict_for(row, {"pbo_status": "insufficient_windows"})
    assert verdict == "CANNOT_DETERMINE"
    assert "did not run" in reason


def test_the_observation_floor_is_derived_from_the_vendored_module():
    """A local floor would be a second opinion about the same refusal."""
    from backend.strategy import multipletesting as MT
    assert E5.MIN_DSR_OBSERVATIONS == MT.MIN_OBSERVATIONS
    from learner import evidence_memory as EM
    assert (E5.DSR_BAR, E5.PBO_BAR) == (EM.DSR_BAR, EM.PBO_BAR)


# -------------------------------------------------- the exclusion is real

def test_a_deprioritized_lineage_is_excluded_from_the_carried_elites(tmp_path):
    """The verdict has to CHANGE something. `update_elites` drops the banned
    lineage from both this night's rows and the elites already carried."""
    from scripts.night_checkpoint import SearchState

    state = SearchState(tmp_path / "state.json")
    rows = [{"key": "a", "lineage": "LA", "genome": {"k": 1}, "fitness": 9.0,
             "banks_met": 5},
            {"key": "b", "lineage": "LB", "genome": {"k": 2}, "fitness": 8.0,
             "banks_met": 4}]
    state.update_elites(rows, keep=24)
    assert {e["lineage"] for e in state.elites} == {"LA", "LB"}

    # LA is deprioritized tonight: it must leave the CARRIED set too, not just
    # be skipped on the way in.
    state.update_elites([], keep=24, exclude_lineages={"LA"})
    assert {e["lineage"] for e in state.elites} == {"LB"}
    # and a fresh row from the banned lineage does not get back in
    state.update_elites([{"key": "a2", "lineage": "LA", "genome": {"k": 3},
                          "fitness": 99.0, "banks_met": 9}], keep=24,
                        exclude_lineages={"LA"})
    assert "LA" not in {e["lineage"] for e in state.elites}
    assert state.seed_population(5) == [{"k": 2}]


def test_deprioritized_lineages_reads_the_LATEST_verdict_per_lineage(tmp_path):
    """Append-only means a lineage's history contains both verdicts. The
    exclusion follows the most recent one, or a lineage could never be
    rehabilitated by measuring it better."""
    p = tmp_path / E5.VERDICTS_NAME
    E5.append_verdicts(p, [{"lineage": "L1", "verdict": "DEPRIORITIZED"},
                           {"lineage": "L2", "verdict": "ACTIVE"}])
    assert E5.deprioritized_lineages(p) == {"L1"}
    E5.append_verdicts(p, [{"lineage": "L1", "verdict": "ACTIVE"},
                           {"lineage": "L2", "verdict": "DEPRIORITIZED"}])
    assert E5.deprioritized_lineages(p) == {"L2"}


def test_an_absent_verdicts_file_is_an_empty_set_not_a_crash(tmp_path):
    assert E5.deprioritized_lineages(tmp_path / "nothing.jsonl") == set()


# ----------------------------------------------------- the job end to end

def test_the_job_writes_its_receipt_and_refuses_an_empty_log(tmp_path):
    log = tmp_path / "G3_evaluations.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in _cohort(6, 40)),
                   encoding="utf-8")
    payload = E5.E5_stopping_rules(logs=[log], out_dir=tmp_path)
    assert payload["job"] == "E5_stopping_rules"
    assert payload["n_evaluation_rows"] == 6 * 40
    assert payload["n_trials_effective_onc"] is None
    assert (tmp_path / E5.VERDICTS_NAME).is_file()
    assert payload["counts"]

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    nothing = E5.E5_stopping_rules(logs=[empty], out_dir=tmp_path / "e")
    assert nothing["counts"] == {}
    assert nothing["verdict"].startswith("NO LINEAGE ADMITTED")


def test_the_matrix_keeps_only_COMPLETE_rows():
    """A bank where one finalist has a number and the other does not is not a
    comparison; CSCV would rank a strategy against itself."""
    rows = [_eval_row("x", "LX", 1, 1.0), _eval_row("x", "LX", 2, 2.0),
            _eval_row("y", "LY", 2, 3.0), _eval_row("y", "LY", 3, 4.0)]
    built = E5.lineage_table(rows, min_banks=2)
    frame, note = E5.performance_matrix(built["table"])
    assert list(frame.index) == [2], note
    assert "1 of them complete" in note


@pytest.mark.parametrize("bad", [[1.0] * 40, []])
def test_a_degenerate_vector_refuses_rather_than_returning_a_number(bad):
    row = E5.dsr_row(bad, n_trials=10, trial_sharpe_std=1.0)
    assert row["dsr"] is None
    assert row["dsr_status"] in ("no_dispersion", "insufficient_observations")
