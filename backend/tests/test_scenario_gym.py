"""The scenario gym: the fiction, the twins, the grader and the adoption cap.

No model is called and `backend/data` is never read. Every test here hands the
job's own functions synthetic answers with a KNOWN sign accuracy and a KNOWN
twin-movement share and checks the number that comes back -- the one shape of
test that can catch a grader agreeing with itself.

The four things this file is here to keep true:

1. the masking is X_anon_gap's function, not a copy of it;
2. a twin is deterministic and its appended development is genuinely new text
   (a twin that varies nothing is the same scenario asked twice);
3. a reply that fails the schema is REFUSED_SCHEMA and is COUNTED -- never
   repaired, never retried;
4. `reliability_weight` is 0 and the receipt says NOT_ADOPTED, in code rather
   than in an intention (spec section C rule 4, section E's named failure).
"""

from __future__ import annotations

import inspect
import json
import re

import pytest

from backend import config
from backend.services import decision_contract as dc
from backend.services import event_vocabulary as vocab
from backend.services import protocol_p16 as pp
from scripts import night_r2_monthly_llm as R2
from scripts import night_scenario_gym as S

SEED = 20260920
MONTHS = [f"2025-{i:02d}" for i in range(1, 13)]


# --------------------------------------------- 1. the masking is BORROWED

def test_the_gym_masks_with_the_same_function_x_anon_gap_masks_with():
    """Not "the same rule" -- the same object. Two maskers drift; one cannot."""
    from scripts import night_x_anonymisation_gap as X

    assert S.widened_digests is R2.widened_digests
    assert X.widened_digests is R2.widened_digests
    assert S.widened_cells_and_docs is R2.widened_cells_and_docs
    # and the draw, the fingerprint and the grading arithmetic likewise
    assert S.grade is R2.grade and S.paired_vs is R2.paired_vs


def test_the_mask_underneath_is_r7s_mask_company():
    from scripts.r7_news_representation import CO_TOKEN, mask_company, tokenise

    toks = mask_company(tokenise("AAPL said Apple will ship."), "AAPL", {"apple"})
    assert CO_TOKEN in toks and "AAPL" not in toks


# -------------------------------------------- 2. the fiction: shifted dates

def test_dates_move_and_numbers_do_not():
    text = ("Filed 2025-06-17; guidance given June 3, 2025 and confirmed "
            "17 June 2025, for June 2025. EPS $0.34 on 1,200 units, up 12.5%, "
            "2025 employees 4,000.")
    out = S.shift_dates(text, 200)
    for number in ("$0.34", "1,200", "12.5%", "4,000"):
        assert number in out, f"{number} is a NUMBER and must survive verbatim"
    assert "2025-06-17" not in out and "2026-01-03" in out
    assert "June 3, 2025" not in out
    assert "17 June 2025" not in out


def test_a_zero_offset_is_the_identity():
    text = "Filed 2025-06-17, June 2025."
    assert S.shift_dates(text, 0) == text


def test_one_pass_only_a_day_month_year_is_not_shifted_twice():
    """`17 June 2025` -> `3 January 2026`; four separate subs would then match
    `January 2026` again and shift it a second time."""
    assert S.shift_dates("17 June 2025", 200) == "3 January 2026"
    assert S.shift_dates("June 2025", 200) == "January 2026"


def test_an_impossible_date_literal_is_left_exactly_as_written():
    assert S.shift_dates("filed 2025-02-31 late", 30) == "filed 2025-02-31 late"


def test_the_date_offset_is_per_cell_deterministic_and_inside_the_declared_range():
    lo, hi = config.SCENARIO_GYM_DATE_SHIFT_DAYS
    a = S.cell_offset(("AAPL", "2025-06"), SEED)
    assert a == S.cell_offset(("AAPL", "2025-06"), SEED)
    assert a != S.cell_offset(("MSFT", "2025-06"), SEED)
    assert a != S.cell_offset(("AAPL", "2025-06"), SEED + 1)
    for cell in (("AAPL", "2025-06"), ("MSFT", "2025-01"), ("XYZ", "2026-03")):
        assert lo <= abs(S.cell_offset(cell, SEED)) <= hi


# --------------------------------------- 3. the twins: deterministic, disjoint

def test_every_vocabulary_id_is_keyed_to_a_development_family():
    """Derived from the vocabulary, so a v4 id is a RED SUITE and not a silent
    fall through to the generic pair while the receipt claims the twin was
    keyed by the dominant event."""
    assert S.unmapped_event_ids() == [], (
        "these vocabulary ids have no development family: "
        f"{S.unmapped_event_ids()}")
    assert set(S.EVENT_FAMILY.values()) <= set(S.DEVELOPMENT_FAMILIES)


def test_the_twins_are_deterministic_and_the_library_hash_is_stable():
    digest = "- [co] reported results for the period on 2025-06-17."
    one = S.build_case(digest, ("AAPL", "2025-06"), "earnings_report", seed=SEED)
    two = S.build_case(digest, ("AAPL", "2025-06"), "earnings_report", seed=SEED)
    assert one == two
    assert S.library_hash() == S.library_hash()
    assert len(S.library_hash()) == 64


def test_a_twin_is_the_base_byte_identical_plus_one_appended_line():
    digest = "- [co] reported results on 2025-06-17.\n- A supplier commented."
    case = S.build_case(digest, ("AAPL", "2025-06"), "earnings_report", seed=SEED)
    base = case["texts"]["real"]
    for arm in S.TWIN_ARMS:
        twin = case["texts"][arm]
        assert twin.startswith(base), f"{arm} changed the base setup"
        tail = twin[len(base):]
        assert tail.count("\n") == 1, f"{arm} appended more than one line"
        assert case["appended"][arm] in tail


def test_the_appended_development_is_disjoint_from_the_real_text():
    digest = "- [co] reported results on 2025-06-17."
    case = S.build_case(digest, ("AAPL", "2025-06"), "earnings_report", seed=SEED)
    assert all(case["disjoint"].values())
    for arm in S.TWIN_ARMS:
        assert case["appended"][arm] not in case["texts"]["real"]
    # and the check is a real check: a base that already contains the sentence
    # is reported as NOT disjoint rather than passing quietly
    good = S.developments_for("earnings_report")["good"]
    assert S.is_disjoint("- nothing like it", good) is True
    assert S.is_disjoint(f"- {good}", good) is False


def test_the_good_and_bad_twins_differ_and_the_control_is_unrelated():
    case = S.build_case("- [co] filed.", ("AAPL", "2025-06"),
                        "regulatory_investigation_or_action", seed=SEED)
    assert case["appended"]["good_twin"] != case["appended"]["bad_twin"]
    assert case["family"] == "regulatory"
    assert case["control_family"] != case["family"]
    # the controls are SIGN-MATCHED: an unrelated favourable development for
    # the good twin, an unrelated adverse one for the bad twin. One favourable
    # control for both is what made the first smoke run's bad-twin lift a
    # measure of valence rather than relevance.
    assert set(S.TWIN_CONTROL) == {"good_twin", "bad_twin"}
    assert S.TWIN_CONTROL["good_twin"] == ("control_good_twin", "up")
    assert S.TWIN_CONTROL["bad_twin"] == ("control_bad_twin", "down")
    ctl_good, ctl_bad = S.DEVELOPMENT_FAMILIES[case["control_family"]]
    assert case["appended"]["control_good_twin"] == ctl_good
    assert case["appended"]["control_bad_twin"] == ctl_bad
    for arm in S.TWIN_ARMS:
        assert case["appended"][arm] not in (
            [v for a, v in case["appended"].items() if a != arm])


def test_the_twin_carries_the_vocabularys_own_direction_prior():
    """The twins are built from the vocabulary's priors, not the model's."""
    dev = S.developments_for("dividend_cut_or_suspension")
    assert dev["direction_prior"] == vocab.by_id(
        "dividend_cut_or_suspension").direction_prior == -1
    assert dev["keyed"] is True
    # an id that is not in the vocabulary at all still returns a usable pair,
    # and says it was not keyed rather than pretending it was
    unknown = S.developments_for("not_a_real_event_id")
    assert unknown["keyed"] is False and unknown["family"] == "generic"


def test_no_model_writes_a_twin():
    """The library is a literal table; nothing in the twin path can call out."""
    src = inspect.getsource(S.build_case) + inspect.getsource(S.developments_for)
    for forbidden in ("fi.complete", "complete(", "_ask("):
        assert forbidden not in src


# ------------------------------------------------- 4. the decision schema

def test_the_system_message_carries_the_whole_schema():
    """2026-09-13, paid for at 54% refusals: a prompt that REFERS to a schema
    it never sends is a prompt whose enum the model invents."""
    fp = S.prompt_fingerprint()
    assert fp["schema_in_system"] is True
    for field in S.DECISION_SCHEMA["required"]:
        assert f'"{field}"' in S.SYSTEM
    for direction in S.DIRECTIONS:
        assert f'"{direction}"' in S.SYSTEM
    assert fp["temperature"] == 0.0
    assert len(fp["system_sha256"]) == 64


GOOD = {"direction": "BUY", "size_pct": 2.5, "expected_return_20d": 1.8,
        "confidence": 0.6, "falsifier": "the next filing restates the quarter"}


def test_a_well_formed_decision_validates():
    assert S.validate_decision(GOOD) == []
    obj, reasons = S.parse_decision("Here you go: " + json.dumps(GOOD))
    assert reasons == [] and obj == GOOD


@pytest.mark.parametrize("mutation,field", [
    ({"direction": "LONG"}, "direction"),
    ({"size_pct": 42.0}, "size_pct"),
    ({"size_pct": "2.5"}, "size_pct"),
    ({"confidence": 1.7}, "confidence"),
    ({"confidence": True}, "confidence"),
    ({"expected_return_20d": "up"}, "expected_return_20d"),
    ({"falsifier": ""}, "falsifier"),
    ({"conviction": 9}, "conviction"),
])
def test_a_malformed_decision_is_refused_naming_the_field(mutation, field):
    bad = {**GOOD, **mutation}
    reasons = S.validate_decision(bad)
    assert reasons, f"{mutation} should not validate"
    assert any(r.startswith(field) for r in reasons), reasons


def test_a_missing_field_is_named():
    bad = {k: v for k, v in GOOD.items() if k != "falsifier"}
    assert "falsifier: missing" in S.validate_decision(bad)


def test_prose_and_broken_json_are_refused_rather_than_repaired():
    for reply in ("I would probably buy here.", "", "{not json at all}",
                  '{"direction": "BUY"'):
        obj, reasons = S.parse_decision(reply)
        assert obj is None and reasons


# ------------------------------------ 5. the grader, on a KNOWN synthetic set

def _row(arm, name, month, direction, *, size, conf, er, fwd, refusal=None):
    case = {"cell": [name, month], "event_type": "earnings_report",
            "family": "analyst"}
    d = None if refusal else {"direction": direction, "size_pct": size,
                              "confidence": conf, "expected_return_20d": er,
                              "falsifier": "x"}
    return S.decision_row(case, arm, d, fwd=fwd, refusal=refusal)


def _known_set(n_per_month=4, good_moves=True, bad_moves=True,
               control_moves=False, right=3):
    """`n_per_month` names a month over twelve months.

    `right` of every four real decisions call the sign correctly, so the known
    sign accuracy is exactly `right / 4`.
    """
    rows = {a: [] for a in S.ARMS}
    for m in MONTHS:
        for i in range(n_per_month):
            name = f"N{i}"
            fwd = 0.05 if i % 2 == 0 else -0.05
            correct = i < right
            direction = "BUY" if (fwd > 0) == correct else "SHORT"
            rows["real"].append(_row("real", name, m, direction, size=2.0,
                                     conf=0.6, er=1.0, fwd=fwd))
            rows["control_shuffled"].append(
                _row("control_shuffled", name, m, "BUY", size=2.0, conf=0.6,
                     er=1.0, fwd=fwd))
            g = 1.0 if good_moves else 0.0
            b = 1.0 if bad_moves else 0.0
            c = 1.0 if control_moves else 0.0
            rows["good_twin"].append(
                _row("good_twin", name, m, direction, size=2.0 + g,
                     conf=0.6 + 0.1 * g, er=1.0 + g, fwd=fwd))
            rows["bad_twin"].append(
                _row("bad_twin", name, m, direction, size=2.0 - b,
                     conf=0.6 - 0.1 * b, er=1.0 - b, fwd=fwd))
            rows["control_good_twin"].append(
                _row("control_good_twin", name, m, direction, size=2.0 + c,
                     conf=0.6 + 0.1 * c, er=1.0 + c, fwd=fwd))
            rows["control_bad_twin"].append(
                _row("control_bad_twin", name, m, direction, size=2.0 - c,
                     conf=0.6 - 0.1 * c, er=1.0 - c, fwd=fwd))
    return rows


def test_the_grader_reproduces_a_known_sign_accuracy():
    assert S.grade_and_adopt(_known_set(right=3))["arms"]["real"][
        "sign_accuracy"] == pytest.approx(0.75)
    assert S.grade_and_adopt(_known_set(right=4))["arms"]["real"][
        "sign_accuracy"] == pytest.approx(1.0)
    assert S.grade_and_adopt(_known_set(right=0))["arms"]["real"][
        "sign_accuracy"] == pytest.approx(0.0)


def test_the_grader_reproduces_a_known_twin_movement_share():
    """Every good twin moves up, every bad twin moves down, the control does
    not move at all -- so the two strict rates are 1.0, the gut score is 1.0
    and the lift over the control is the whole 100 pp."""
    out = S.grade_and_adopt(_known_set())["PRIMARY_twin_movement"]
    assert out["good_twin"]["up_strict_rate"] == pytest.approx(1.0)
    assert out["bad_twin"]["down_strict_rate"] == pytest.approx(1.0)
    assert out["control_good_twin"]["unmoved_rate"] == pytest.approx(1.0)
    assert out["control_bad_twin"]["unmoved_rate"] == pytest.approx(1.0)
    assert out["gut_score"] == pytest.approx(1.0)
    assert out["good_twin_lift_vs_control"]["lift_pp"] == pytest.approx(100.0)
    assert out["bad_twin_lift_vs_control"]["lift_pp"] == pytest.approx(100.0)
    assert out["gut_score_vs_control_pp"] == pytest.approx(100.0)


def test_a_model_that_never_moves_scores_zero_on_the_strict_rate():
    """The spec's literal pass condition is `delta >= 0 on a majority`, which a
    constant model passes at 100%. That reading is REPORTED; the strict rate is
    what the headline and the lift are built from."""
    out = S.grade_and_adopt(_known_set(good_moves=False, bad_moves=False)
                            )["PRIMARY_twin_movement"]
    assert out["good_twin"]["up_or_flat_rate"] == pytest.approx(1.0)
    assert out["good_twin"]["up_strict_rate"] == pytest.approx(0.0)
    assert out["bad_twin"]["down_strict_rate"] == pytest.approx(0.0)
    assert out["gut_score"] == pytest.approx(0.0)


def test_a_gut_that_moves_no_more_than_the_unrelated_sentence_has_no_lift():
    """"A gut that doesn't move on the bad twin is not a gut" -- and one that
    moves just as much on an unrelated appended sentence is not one either."""
    out = S.grade_and_adopt(_known_set(control_moves=True))["PRIMARY_twin_movement"]
    assert out["good_twin"]["up_strict_rate"] == pytest.approx(1.0)
    assert out["bad_twin"]["down_strict_rate"] == pytest.approx(1.0)
    assert out["good_twin_lift_vs_control"]["lift_pp"] == pytest.approx(0.0)
    assert out["bad_twin_lift_vs_control"]["lift_pp"] == pytest.approx(0.0)


def test_each_twin_is_differenced_against_a_control_of_its_own_sign():
    """The lift must isolate RELEVANCE, not valence. With one favourable
    control for both twins, a model that simply follows the tone of the last
    appended sentence scores a large bad-twin lift for the wrong reason --
    which is exactly what the first smoke run reported (+52.6 pp, t 3.89)."""
    out = S.grade_and_adopt(_known_set(control_moves=True))["PRIMARY_twin_movement"]
    assert out["good_twin_lift_vs_control"]["control_rate"] == pytest.approx(1.0)
    assert out["bad_twin_lift_vs_control"]["control_rate"] == pytest.approx(1.0)
    assert "UNRELATED favourable" in out["good_twin_lift_vs_control"]["label"]
    assert "UNRELATED adverse" in out["bad_twin_lift_vs_control"]["label"]


def test_a_direction_flip_is_counted():
    rows = _known_set()
    for r in rows["bad_twin"]:
        r["direction"], r["dir"] = "SHORT", -1
    out = S.grade_and_adopt(rows)["PRIMARY_twin_movement"]
    # half the real rows are SHORT already, so some but not all pairs flip
    assert 0.0 < out["bad_twin"]["direction_flip_rate"] < 1.0


def test_a_refused_row_is_excluded_from_every_pairing_and_still_counted():
    rows = _known_set()
    rows["real"][0]["refusal_class"] = "REFUSED_SCHEMA"
    out = S.grade_and_adopt(rows, refusals={"REFUSED_SCHEMA": 1})
    assert out["refusals"]["REFUSED_SCHEMA"] == 1
    assert out["PRIMARY_twin_movement"]["good_twin"]["n_pairs"] == 47


def test_movement_refuses_when_the_arms_do_not_share_their_blocks():
    rows = _known_set()
    a = S.movement(rows["real"], rows["good_twin"], "good_twin")
    b = dict(a)
    b["_blocks"] = list(reversed(a["_blocks"]))
    assert "REFUSED" in str(S.movement_lift(a, b, "up", "x").get("verdict"))


# ----------------------------------------- 6. the refusals and the adoption

def test_every_refusal_class_is_listed_even_when_none_fired():
    out = S.grade_and_adopt(_known_set())
    for cls in S.REFUSAL_CLASSES:
        assert cls in out["refusals"], f"{cls} is missing from the receipt"
    assert out["refusals"]["PENDING_MODEL"] == 0
    assert out["refusals"]["REFUSED_SCHEMA"] == 0
    assert out["refusals"]["REFUSED_LANGUAGE"] == 0
    assert out["refusals"]["INSUFFICIENT_N"] == 0


def test_a_short_run_refuses_the_calibration_by_name_rather_than_binning_noise():
    out = S.grade_and_adopt(_known_set(n_per_month=1))   # 12, under the floor
    assert out["calibration"]["refusal_class"] == "INSUFFICIENT_N"
    assert out["calibration"]["ece"] is None
    assert out["refusals"]["INSUFFICIENT_N"] == 1


def test_every_refusal_class_lands_in_a_decision_contract_terminal_state():
    """Not a third taxonomy: four reader-side names, each mapped to one of the
    18 states `decision_contract` already declares."""
    assert S.unknown_terminal_states() == []
    assert set(S.REFUSAL_TERMINAL_STATE) == set(S.REFUSAL_CLASSES)
    for state in S.REFUSAL_TERMINAL_STATE.values():
        assert state in dc.TERMINAL_STATES


def test_the_adoption_line_is_present_and_says_not_adopted():
    out = S.grade_and_adopt(_known_set())
    line = out["adoption_line"]
    assert "NOT_ADOPTED" in line
    assert "reliability_weight 0" in line
    assert f"N>={config.SCENARIO_GYM_ADOPT_MIN_N}" in line
    assert "forward record" in line
    assert out["adoption"]["line"] == line
    assert out["adoption"]["state"] == "NOT_ADOPTED"
    assert out["adoption"]["reliability_weight"] == 0.0


def test_the_weight_stays_at_zero_even_with_n_and_a_forward_record():
    """The cap is in CODE. A measured resolution is carried BESIDE the weight,
    labelled as what it would be, and never becomes the weight by itself."""
    calib = {"brier_decomposition": {"resolution": 0.08}}
    for n, fwd in ((10, False), (10, True),
                   (config.SCENARIO_GYM_ADOPT_MIN_N, False),
                   (config.SCENARIO_GYM_ADOPT_MIN_N, True)):
        out = S.adoption(n, calib, forward_record=fwd)
        assert out["reliability_weight"] == 0.0
        assert out["reliability_weight_measured_not_granted"] == 0.08
        assert "veto" in out["never"]


def test_below_the_floor_the_adoption_says_why_by_name():
    out = S.adoption(12, {})
    assert "N 12 < 300" in out["why_not"]
    assert "no forward record" in out["why_not"]


def test_the_gym_can_never_become_a_trading_arm_by_its_own_receipt():
    out = S.grade_and_adopt(_known_set())
    assert "never deciding" in out["secondary_returns"]["caution"]
    assert out["adoption"]["entered_as"].startswith("candidate field only")


# ------------------------------------------------------ 7. the MDE and P1-P6

def test_the_primary_mde_is_the_block_one_and_both_are_printed():
    m = S.grade_and_adopt(_known_set(), sd_pct=17.39)["MDE"]
    assert "PRIMARY_block_level" in m and "secondary_per_decision" in m
    assert "block" in m["which_decides"].lower()
    assert m["secondary_per_decision"]["cross_sectional_sd_pct"] == pytest.approx(17.39)
    assert m["secondary_per_decision"]["MDE_mean_20d_pp"] is not None


def test_the_mde_refuses_rather_than_quoting_a_constant_it_did_not_measure():
    m = S.mde(0, None)
    assert m["secondary_per_decision"]["MDE_mean_20d_pp"] is None
    assert "CANNOT DETERMINE" in m["PRIMARY_block_level"]["basis"]


def test_the_protocol_block_this_job_writes_is_valid():
    out = S.grade_and_adopt(_known_set(), sd_pct=17.39)
    payload = {
        "job": S.JOB, "lane": S.LANE,
        "P1_P6": S._protocol({"masked_digests": "cells.json",
                              "shuffled_control": "answers.jsonl"},
                             flip_rate=0.1, flip_n=48, realised_bps=50.0,
                             calib=out["calibration"]),
        "LAP": pp.lap(False, reason="PANEL-B is entirely post-cutoff"),
        "anonymisation_gap": pp.anonymisation_gap(reason="every arm reads masked text"),
    }
    assert pp.validate(payload) == []


def test_a_receipt_with_nothing_read_claims_no_control_it_did_not_run():
    block = S._protocol({}, nothing_was_read=True)
    p1 = block["P1_temporal_integrity"]
    assert p1["anonymised"] is False and p1["evidence_paths"]["anonymised"] is None
    assert pp.validate({"job": S.JOB, "lane": S.LANE, "P1_P6": block,
                        "LAP": pp.lap(False, reason="post-cutoff"),
                        "anonymisation_gap": pp.anonymisation_gap(
                            reason="nothing was read")}) == []


# ------------------------------------------ 8. the job's wiring and cursor

def test_the_job_is_registered_resumable_and_staged():
    from scripts.night_factory_jobs import JOB_STAGES, JOBS, RESUMABLE

    assert "S2_scenario_gym" in JOBS
    assert JOB_STAGES["S2_scenario_gym"] == "features"
    assert "S2_scenario_gym" in RESUMABLE


def test_the_job_never_starts_the_model_server():
    """The desktop shell owns llama-server's lifecycle. A research job that
    boots an 8 GB server collides with another one mid-run."""
    src = inspect.getsource(S)
    for forbidden in ("llama-start", "subprocess.Popen", "os." + "system",
                      "taskkill", "start_server"):
        assert forbidden not in src, f"the gym must not contain {forbidden}"


def test_the_cells_sidecar_name_cannot_be_read_as_a_receipt():
    """`night_leaderboard_sync.RECEIPT` is `^(?P<job>.+)_run(\\d{2})\\.json$`,
    so the suffix has to come AFTER the run number or the sidecar reaches the
    board as a job with no P1-P6 block."""
    receipt = re.compile(r"^(?P<job>.+)_run(\d{2})\.json$")
    assert receipt.match("S2_scenario_gym_run01.json")
    assert not receipt.match("S2_scenario_gym_run01_cells.json")
    assert not receipt.match("S2_scenario_gym_run01_smoke.json")


def test_the_cursor_is_derived_from_the_answers_file(tmp_path):
    """A separate cursor file can disagree with the answers beside it."""
    path = tmp_path / "answers.jsonl"
    path.write_text(
        json.dumps({"tag": "real", "name": "AAPL", "month": "2025-06"}) + "\n"
        + json.dumps({"tag": "good_twin", "name": "AAPL", "month": "2025-06"}) + "\n"
        + "{ half written\n",
        encoding="utf-8")
    done = S._answered(path)
    assert ("real", "AAPL", "2025-06") in done
    assert ("bad_twin", "AAPL", "2025-06") not in done
    assert len(done) == 2
    assert S._answered(tmp_path / "nothing.jsonl") == set()


def test_the_dominant_event_falls_back_to_no_event_and_counts_it(tmp_path):
    (tmp_path / "2026-09-13.jsonl").write_text(
        "\n".join(json.dumps(r) for r in [
            {"scope": "AAPL", "scope_kind": "ticker", "document_date": "2025-06-04",
             "event_type": "earnings_report"},
            {"scope": "AAPL", "scope_kind": "ticker", "document_date": "2025-06-19",
             "event_type": "earnings_report"},
            {"scope": "AAPL", "scope_kind": "ticker", "document_date": "2025-06-21",
             "event_type": "litigation_filed"},
            {"scope": "MSFT", "scope_kind": "ticker", "document_date": "2025-06-02",
             "event_type": "stock_buyback"},
        ]) + "\n", encoding="utf-8")
    # a refusals file is not a typed row and must not be read
    (tmp_path / "2026-09-13_refusals.jsonl").write_text(
        json.dumps({"scope": "ZZZZ", "scope_kind": "ticker",
                    "document_date": "2025-06-02",
                    "event_type": "mergers_acquisitions"}) + "\n", encoding="utf-8")
    keys = [("AAPL", "2025-06"), ("MSFT", "2025-06"), ("ZZZZ", "2025-06")]
    events, cov = S.dominant_events(keys, path=tmp_path)
    assert events[("AAPL", "2025-06")] == "earnings_report"     # the mode, 2 of 3
    assert events[("MSFT", "2025-06")] == "stock_buyback"
    assert events[("ZZZZ", "2025-06")] == vocab.NO_EVENT
    assert cov["cells_with_a_typed_event"] == 2 and cov["cells"] == 3
    assert cov["coverage"] == pytest.approx(2 / 3, abs=1e-4)
    assert cov["typed_event_files_read"] == 1


def test_a_missing_typed_event_folder_is_a_named_zero_not_a_crash(tmp_path):
    events, cov = S.dominant_events([("AAPL", "2025-06")], path=tmp_path / "nope")
    assert events[("AAPL", "2025-06")] == vocab.NO_EVENT
    assert cov["coverage"] == 0.0 and cov["typed_event_files_read"] == 0
