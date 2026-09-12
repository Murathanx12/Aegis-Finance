"""L3: a planted lookahead is detected, a clean set is not flagged.

The spec's own known answers (section 7, step 3) are the first two tests here.
The third and fourth are the ones that make the detector honest: a set with no
pre-cutoff cells is INCONCLUSIVE rather than CLEAN, and a confident-but-WRONG
recall scores LAP zero rather than inflating it.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from backend.services import protocol_p16 as pp
from scripts import night_l3_lookahead as L3

PRE_MONTHS = [f"2023-{m:02d}" for m in range(1, 13)] + [f"2024-{m:02d}" for m in range(1, 7)]
POST_MONTHS = [f"2024-{m:02d}" for m in range(7, 13)] + [f"2025-{m:02d}" for m in range(1, 13)]


def _rows(months, *, planted: bool, seed: int, n_per_month: int = 24):
    """Synthetic regression rows.

    `planted=True` reproduces the spec's own case: accuracy 0.9 where LAP > 0.5,
    0.5 (a coin flip) everywhere else. The forecast (the model's confidence) is
    drawn INDEPENDENTLY of both, which is what makes this case load on the LAP
    LEVEL rather than on the interaction -- and is why the verdict tests the
    two jointly.
    """
    rng = np.random.default_rng(seed)
    out = []
    for m in months:
        for i in range(n_per_month):
            lap = float(rng.uniform(0, 1))
            conf = float(rng.uniform(0.3, 0.9))
            p_hit = 0.9 if (planted and lap > 0.5) else 0.5
            out.append({"name": f"S{i}", "month": m, "block": m,
                        "accuracy": float(rng.uniform() < p_hit),
                        "forecast": conf, "LAP": lap,
                        "era": "pre" if m < "2024-07" else "post"})
    return out


def test_a_planted_lookahead_is_detected():
    """Spec section 7 step 3, first half: accuracy concentrated in high-LAP cells
    pre-cutoff and nowhere post-cutoff must come out CONTAMINATED, and the
    post-cutoff interaction must NOT be significant."""
    pre = L3.interaction_test(_rows(PRE_MONTHS, planted=True, seed=1, n_per_month=60))
    post = L3.interaction_test(_rows(POST_MONTHS, planted=False, seed=2, n_per_month=60))
    verdict, why = L3.verdict_of(pre, post)
    assert verdict == "CONTAMINATED", (why, pre, post)
    assert post["joint_p"] > 0.05, "the post-cutoff arm must be the falsifier"
    assert "beta2" in pre["carried_by"], (
        "the spec's planted case is a LAP LEVEL effect; the receipt must say so")


def test_a_clean_set_is_not_flagged():
    """Spec section 7 step 3, second half -- AND the proof that CLEAN is
    reachable at all. A gate that cannot go green is a broken gate, so the
    sample here is one that can actually resolve beta3 (MDE below 1.0)."""
    pre = L3.interaction_test(_rows(PRE_MONTHS, planted=False, seed=3, n_per_month=60))
    post = L3.interaction_test(_rows(POST_MONTHS, planted=False, seed=4, n_per_month=60))
    verdict, why = L3.verdict_of(pre, post)
    assert verdict == "CLEAN", (why, pre["joint_p"], post["joint_p"])
    assert pre["mde_beta3"] is not None and pre["mde_beta3"] < L3.MDE_CEILING


def test_an_unresolvable_arm_is_inconclusive_even_when_nothing_is_significant():
    """Spec section 1.5: report the MDE even when CLEAN, so a CLEAN verdict
    cannot hide behind zero power. Here it does not merely get reported -- it
    OVERRIDES. Measured on 2026-09-12, PANEL-B's own size (435 gradeable cells
    over 18 month blocks, about 24 a month) puts the MDE on beta3 right at the
    1.0 ceiling (0.99-1.25 across seeds), so even with the probe run PANEL-B is
    at the edge of resolving anything; at 12 cells a month it is clearly past
    it."""
    thin = L3.interaction_test(_rows(PRE_MONTHS, planted=False, seed=21, n_per_month=12))
    assert thin["mde_beta3"] > L3.MDE_CEILING, thin["mde_beta3"]
    # this arm is pure noise AND its joint p came out significant: an arm that
    # cannot resolve anything must not be stamped CONTAMINATED either
    assert thin["joint_p"] < 0.05
    post = L3.interaction_test(_rows(POST_MONTHS, planted=False, seed=22, n_per_month=60))
    verdict, why = L3.verdict_of(thin, post)
    assert verdict == "INCONCLUSIVE_UNDERPOWERED" and "zero power" in why


def test_a_true_interaction_is_carried_by_beta3_and_named():
    """When the skill really does scale with the forecast x LAP product, the
    receipt must attribute it to beta3 rather than to the level.

    The DGP is centred so the two MAIN effects are zero by construction: hit
    probability moves only with `(conf - 0.6) * (LAP - 0.5)`. A model that is
    right where it is confident AND where it already knew, and no better than
    a coin flip when only one of the two is high, is the shape beta3 exists to
    catch -- as opposed to the spec's own planted case, which is a level."""
    rng = np.random.default_rng(5)
    rows = []
    for m in PRE_MONTHS:
        for i in range(60):
            lap = float(rng.uniform(0, 1))
            conf = float(rng.uniform(0.3, 0.9))
            p_hit = min(max(0.5 + 1.6 * (conf - 0.6) * (lap - 0.5), 0.02), 0.98)
            rows.append({"name": f"S{i}", "month": m, "block": m,
                         "accuracy": float(rng.uniform() < p_hit),
                         "forecast": conf, "LAP": lap, "era": "pre"})
    pre = L3.interaction_test(rows)
    post = L3.interaction_test(_rows(POST_MONTHS, planted=False, seed=6, n_per_month=60))
    assert L3.verdict_of(pre, post)[0] == "CONTAMINATED"
    assert pre["beta3"] > 0 and pre["beta3_p"] < 0.05
    assert "beta3" in pre["carried_by"]


def test_significant_in_both_regimes_is_ambiguous_not_contaminated():
    pre = L3.interaction_test(_rows(PRE_MONTHS, planted=True, seed=7, n_per_month=60))
    post = L3.interaction_test(_rows(POST_MONTHS, planted=True, seed=8, n_per_month=60))
    verdict, why = L3.verdict_of(pre, post)
    assert verdict == "AMBIGUOUS", why
    assert "did not hold" in why


def test_significant_only_after_the_cutoff_is_ambiguous():
    pre = L3.interaction_test(_rows(PRE_MONTHS, planted=False, seed=9, n_per_month=60))
    post = L3.interaction_test(_rows(POST_MONTHS, planted=True, seed=10, n_per_month=60))
    verdict, why = L3.verdict_of(pre, post)
    assert verdict == "AMBIGUOUS" and "lookahead cannot produce" in why


def test_an_empty_pre_cutoff_arm_is_inconclusive_not_clean():
    """PANEL-B's real shape. A CLEAN stamp here would be hiding behind zero
    power, which spec section 1.5 forbids by name."""
    post = L3.interaction_test(_rows(POST_MONTHS, planted=False, seed=11, n_per_month=60))
    verdict, why = L3.verdict_of({"n": 0, "note": "no pre-cutoff cells"}, post)
    assert verdict == "INCONCLUSIVE_UNDERPOWERED"
    assert "before/after" in why


def test_three_clusters_is_not_a_standard_error():
    """Nine rows in three month blocks, fitted with four parameters, returned
    joint p = 0.0 on data generated with NO relationship at all -- a sandwich
    estimating a 4x4 covariance from three outer products. The coefficients are
    still reported; the significance is refused, and the verdict is
    INCONCLUSIVE rather than a spurious AMBIGUOUS."""
    pre = L3.interaction_test(_rows(PRE_MONTHS[:3], planted=False, seed=12, n_per_month=3))
    assert pre["joint_p"] is None and str(pre["note"]).count("REFUSED")
    assert pre["beta3"] is not None, "the coefficient is reported, only its p is refused"
    post = L3.interaction_test(_rows(POST_MONTHS, planted=False, seed=13, n_per_month=60))
    verdict, why = L3.verdict_of(pre, post)
    assert verdict == "INCONCLUSIVE_UNDERPOWERED", (why, pre)


# ------------------------------------------------------------------ LAP itself

@pytest.mark.parametrize("d,conf,fwd,expect", [
    (1, 0.9, 0.05, 0.9),        # right direction, confident -> LAP is the confidence
    (1, 0.9, -0.05, 0.0),       # CONFIDENT AND WRONG is a bad memory, not lookahead
    (-1, 0.7, -0.02, 0.7),
    (None, 0.9, 0.05, 0.0),     # UNKNOWN
    (0, 0.9, 0.05, 0.0),        # FLAT anchors nothing
    (1, 0.9, None, 0.0),        # no realised outcome to match
    (1, 5.0, 0.05, 1.0),        # a confidence out of range is clipped, not trusted
])
def test_lap_per_cell(d, conf, fwd, expect):
    assert L3.lap_of(d, conf, fwd) == pytest.approx(expect)


@pytest.mark.parametrize("text,expect", [
    ("RECALL: UP\nCONFIDENCE: 0.8", (1, 0.8)),
    ("RECALL: DOWN\nCONFIDENCE: 0.25", (-1, 0.25)),
    ("RECALL: FLAT\nCONFIDENCE: 0.5", (0, 0.5)),
    ("RECALL: UNKNOWN", (None, 0.0)),
    ("I have no idea", (None, 0.0)),
    ("RECALL: UP", (1, 0.5)),                       # no confidence line -> 0.5
])
def test_the_probe_parser(text, expect):
    assert L3.parse_probe(text) == expect


def test_the_probe_carries_its_own_purpose_tag():
    """Spec section 1.4 step 2: the probe's spend and refusals must never mix
    with R2's own telemetry line."""
    assert L3.LAP_PROBE_PURPOSE == "l3_lap_probe"
    assert "R2" not in L3.LAP_PROBE_PURPOSE


# ---------------------------------------------------------- the accuracy side

def test_the_accuracy_side_reads_r2s_answers_with_r2s_conventions():
    answers = [
        {"tag": "read_MASKED", "name": "A", "month": "2023-05", "dir": 1, "conf": .7, "fwd": .02},
        {"tag": "read_MASKED", "name": "B", "month": "2025-05", "dir": -1, "conf": .6, "fwd": .02},
        {"tag": "read_MASKED", "name": "C", "month": "2025-05", "dir": 0, "conf": .5, "fwd": .02},
        {"tag": "read_MASKED", "name": "D", "month": "2025-05", "dir": 1, "conf": .5, "fwd": None},
        {"tag": "canary_MASKED", "name": "E", "month": "2025-05", "dir": 1, "conf": .5, "fwd": .01},
    ]
    rows = L3.accuracy_rows(answers, "2024-06-30")
    assert len(rows) == 2, "FLAT, unlabelled and canary rows are all excluded"
    assert rows[0]["era"] == "pre" and rows[1]["era"] == "post"
    assert rows[0]["accuracy"] == 1.0 and rows[1]["accuracy"] == 0.0
    s = L3.split_summary(rows)
    assert s["pre"]["cells"] == 1 and s["post"]["cells"] == 1


def test_the_regression_clusters_by_month_block_not_by_cell():
    """435 cells in 18 months is 18 observations wearing 435 hats. A
    cluster-robust SE must be wider than the naive one when the outcome is
    correlated inside a month."""
    rng = np.random.default_rng(19)
    rows = []
    for m in PRE_MONTHS:
        shock = rng.normal(0, 1.0)          # a whole-month shock: within-month dependence
        for i in range(30):
            lap = float(rng.uniform(0, 1))
            conf = float(rng.uniform(0.3, 0.9))
            rows.append({"name": f"S{i}", "month": m, "block": m,
                         "accuracy": float((shock + rng.normal(0, 0.3)) > 0),
                         "forecast": conf, "LAP": lap, "era": "pre"})
    y = np.array([r["accuracy"] for r in rows])
    X = np.column_stack([np.ones(len(rows)), [r["forecast"] for r in rows],
                         [r["LAP"] for r in rows],
                         [r["forecast"] * r["LAP"] for r in rows]])
    clustered = L3.cluster_ols(y, X, [r["block"] for r in rows])
    iid = L3.cluster_ols(y, X, list(range(len(rows))))       # every cell its own cluster
    assert clustered["se"][0] > iid["se"][0], (
        "clustering by month must widen the intercept's SE under a month-level shock")


def test_a_rank_deficient_slice_refuses_rather_than_returning_a_number():
    rows = [{"name": "A", "month": "2023-01", "block": "2023-01", "accuracy": 1.0,
             "forecast": 0.5, "LAP": 0.0, "era": "pre"} for _ in range(20)]
    out = L3.interaction_test(rows)
    assert out["beta3"] is None and out["note"]


# ------------------------------------------------------------ the annotation

def test_a_pre_cutoff_row_is_badged_and_a_post_cutoff_row_is_not():
    pre = {"job": "R2_monthly_llm", "panel": "PANEL-A", "backend": "local_gguf",
           "headline": "2015-2024: ..."}
    post = {"job": "R2_widened_panelB", "panel": "PANEL-B", "backend": "local_gguf",
            "headline": "PANEL-B ..."}
    assert "LAP NOT MEASURED" in L3.lap_annotation("R2_monthly_llm", pre)
    assert L3.lap_annotation("R2_widened_panelB", post) is None


def test_a_row_whose_window_cannot_be_determined_says_unknown_not_post():
    """A guard derives its inputs or refuses. Assuming post-cutoff because the
    receipt forgot to say would silently exempt the rows that most need the badge."""
    note = L3.lap_annotation("Z9_mystery", {"backend": "local_gguf", "headline": "x"})
    assert note and "LAP UNKNOWN" in note


def test_a_non_llm_row_is_never_badged():
    assert L3.lap_annotation("D1_reaction_book", {"headline": "x"}) is None


def test_a_measured_l3_verdict_reaches_the_badge():
    pre = {"panel": "PANEL-A", "backend": "local_gguf", "headline": "x"}
    note = L3.lap_annotation("R2_monthly_llm", pre,
                             {"verdict": "CLEAN", "panel": "PANEL-A", "beta3_pre": 0.01})
    assert "CLEAN" in note and "PANEL-A" in note


def test_the_read_window_is_derived_from_the_receipts_own_fields():
    assert L3.read_window({"year": 2015, "year_to": 2024})[0] == "2015-01"
    assert L3.read_window({"panel": "PANEL-B"})[0] == "2025-01"
    assert L3.read_window({})[0] is None


def test_the_board_calls_the_annotation():
    """AST: `with_lap` must be CALLED where rows are appended, not mentioned."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "scripts" / "night_leaderboard_sync.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    for name in ("main", "rebuild"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        called = {getattr(c.func, "id", None) or getattr(c.func, "attr", None)
                  for c in ast.walk(fn) if isinstance(c, ast.Call)}
        assert "with_lap" in called, f"{name}() appends rows without the LAP annotation"


def test_the_board_annotates_a_pre_cutoff_row(monkeypatch):
    import scripts.night_leaderboard_sync as sync

    monkeypatch.setattr(L3, "latest_l3_receipt", lambda base=None: None)
    out = sync.with_lap("R2_monthly_llm",
                        {"panel": "PANEL-A", "backend": "local_gguf", "headline": "2015-2024"})
    assert out["headline"].startswith("[LAP NOT MEASURED")
    assert out["LAP_note"]
    same = sync.with_lap("D1_reaction_book", {"headline": "x"})
    assert "LAP_note" not in same


# ------------------------------------------------------------------- the job

def test_the_job_refuses_by_name_when_the_reader_is_down(monkeypatch, tmp_path):
    monkeypatch.setattr(L3, "OUT", tmp_path)
    monkeypatch.setattr(L3, "_probe", lambda backend: "ProviderRefusal: local unreachable")
    monkeypatch.setattr(L3.xd, "read_answers", lambda path=None: [
        {"tag": "read_MASKED", "name": "A", "month": "2025-05", "dir": 1,
         "conf": 0.6, "fwd": 0.01}])
    payload = L3.L3_lookahead(run=4)
    assert payload["verdict"].startswith("PENDING_MODEL")
    assert "PRE-cutoff arm is EMPTY" in payload["verdict"]
    assert payload["n_cells_pre_cutoff"] == 0 and payload["n_cells_post_cutoff"] == 1
    assert (tmp_path / "L3_lookahead_run04_cells.json").is_file()
    assert pp.refuse_reasons("L3_lookahead", payload) == []
    assert payload["LAP"]["applies"] is False


def test_panel_a_refuses_because_it_has_no_persisted_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(L3, "OUT", tmp_path)
    payload = L3.L3_lookahead(panel="A", run=5)
    assert payload["verdict"].startswith("REFUSED")
    assert "no persisted per-cell answers" in payload["verdict"]
    assert pp.refuse_reasons("L3_lookahead", payload) == []


def test_a_full_run_with_a_mocked_probe_produces_a_verdict(monkeypatch, tmp_path):
    """The probe half, stubbed end to end: a model that recalls pre-cutoff
    outcomes with varying confidence and nothing post-cutoff, and a read whose
    accuracy rises with that recall. The run must produce a fitted regression,
    a collapsed post-cutoff LAP, and a receipt the protocol accepts.

    Nothing here uses `hash()`: string hashing is salted per process, so a
    fixture built on it is a different fixture every run.
    """
    from types import SimpleNamespace

    rng = np.random.default_rng(31)
    recall = {}          # (name, month) -> (direction word, confidence)
    answers = []
    for m in PRE_MONTHS + POST_MONTHS:
        for i in range(30):
            fwd = float(rng.normal(0, 0.05))
            name = f"S{i}"
            if m < "2024-07":
                conf = 0.5 + 0.5 * ((i * 7) % 10) / 10.0        # deterministic spread
                recall[(name, m)] = ("UP" if fwd > 0 else "DOWN", min(conf, 1.0))
                right = rng.uniform() < min(0.45 + 0.55 * conf, 0.99)
            else:
                right = rng.uniform() < 0.5
            d = int(np.sign(fwd)) or 1
            answers.append({"tag": "read_MASKED", "name": name, "month": m,
                            "dir": d if right else -d,
                            "conf": float(rng.uniform(0.3, 0.9)), "fwd": fwd})

    monkeypatch.setattr(L3, "OUT", tmp_path)
    monkeypatch.setattr(L3, "_probe", lambda backend: None)
    monkeypatch.setattr(L3.xd, "read_answers", lambda path=None: answers)

    import backend.services.free_inference as fi

    def fake(backend, prompt, **kw):
        assert kw.get("purpose") == "l3_lap_probe"
        for (name, month), (word, conf) in recall.items():
            if f"For {name} in {month}," in prompt:
                reply = f"RECALL: {word}\nCONFIDENCE: {conf:.2f}"
                return SimpleNamespace(text=reply, tokens_in=40, tokens_out=8)
        return SimpleNamespace(text="RECALL: UNKNOWN", tokens_in=40, tokens_out=4)

    monkeypatch.setattr(fi, "complete", fake)
    payload = L3.L3_lookahead(run=6)
    assert payload["L3_verdict"] in {"CONTAMINATED", "AMBIGUOUS", "CLEAN",
                                     "INCONCLUSIVE_UNDERPOWERED"}
    assert payload["lap_mean_pre"] > 0.5
    assert payload["lap_mean_post"] == 0.0, "the probe recalls nothing after the cutoff"
    assert payload["beta3_pre"] is not None, payload["regression_pre_cutoff"]
    assert payload["regression_pre_cutoff"]["n_blocks"] == len(PRE_MONTHS)
    assert pp.refuse_reasons("L3_lookahead", payload) == []
    assert payload["LAP"]["applies"] is True
    assert payload["lap_probe"]["cells_probed"] > 0


def test_the_job_is_registered_and_never_starts_the_model_server():
    import ast
    from pathlib import Path

    from scripts import night_factory_jobs as NFJ

    assert "L3_lookahead" in NFJ.JOBS
    src = Path(L3.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Attribute) and node.attr in {"start", "stop", "bind_lifetime"}:
            holder = getattr(node.value, "id", None) or getattr(node.value, "attr", None)
            assert holder not in ("llama_server", "ls")


def test_the_cutoff_table_states_its_source_and_confidence():
    """A scraped system prompt is a source; nothing is not. Every entry must
    carry both, and DeepSeek-R1's inconsistent self-report must not claim a date."""
    for model, row in L3.MODEL_CUTOFFS.items():
        assert row["source"] and row["confidence"] in ("HIGH", "MEDIUM", "LOW"), model
    assert L3.MODEL_CUTOFFS["deepseek-reasoner"]["cutoff"] is None
    assert L3.MODEL_CUTOFFS["deepseek-chat"]["confidence"] == "LOW"


def test_the_receipt_names_its_own_deviation_from_the_spec(monkeypatch, tmp_path):
    monkeypatch.setattr(L3, "OUT", tmp_path)
    monkeypatch.setattr(L3, "_probe", lambda backend: "down")
    monkeypatch.setattr(L3.xd, "read_answers", lambda path=None: [
        {"tag": "read_MASKED", "name": "A", "month": "2025-05", "dir": 1,
         "conf": 0.6, "fwd": 0.01}])
    payload = L3.L3_lookahead(run=8)
    assert any("beta2" in d for d in payload["deviations_from_the_spec"])
    json.dumps(payload)          # the receipt must serialise


def test_a_constant_lap_column_is_refused_not_fitted():
    """A probe that returns the same confidence for every cell makes LAP a
    constant column, collinear with the intercept. No coefficient is
    identified, and the regression must say so rather than return a number."""
    rows = [{"name": f"S{i}", "month": m, "block": m, "accuracy": float(i % 2),
             "forecast": 0.4 + 0.01 * i, "LAP": 0.9, "era": "pre"}
            for m in PRE_MONTHS for i in range(20)]
    out = L3.interaction_test(rows)
    assert out["beta3"] is None and "rank deficient" in out["note"]


@pytest.mark.parametrize("month,cutoff,era", [
    ("2024-05", "2024-06-30", "pre"),
    ("2024-06", "2024-06-30", "pre"),     # a month ENTIRELY inside the window
    ("2024-07", "2024-06-30", "post"),
    ("2024-07", "2024-07-01", "boundary"),  # partly in, partly out: neither arm
    ("2024-08", "2024-07-01", "post"),
    ("2024-05", "2024-07-01", "pre"),
    ("2025-01", None, "post"),
])
def test_the_cutoff_month_is_a_third_answer_not_a_coin_flip(month, cutoff, era):
    """Assigning the cutoff's own month to an arm is a choice nobody made on
    evidence, and it is the kind of choice that decides a borderline verdict.
    Found by a test: `month >= cutoff[:7]` put 2024-06 -- entirely inside a
    2024-06-30 cutoff -- into the POST arm."""
    assert L3.era_of(month, cutoff) == era
