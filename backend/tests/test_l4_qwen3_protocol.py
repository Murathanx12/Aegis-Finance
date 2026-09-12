"""L4: the protocol is the deliverable, so the protocol is what gets tested.

Nothing here measures a model. The reader is DOWN, this job does not start it,
and the one behaviour that matters most is exactly that: a night job that boots
a 17 GiB model because it wanted a number is two sessions fighting over one
card. `test_the_job_never_starts_or_stops_the_server` reads the module's AST --
not a grep, which would match the docstring that explains the ban -- and fails
if `llama_server.start`/`stop`/`bind_lifetime`, or any shell escape, is ever
called from this file.

The rest pins the things a later run could quietly get wrong:

* the prompts are IMPORTED from `r2_trial` and carry its three hashes, so the
  measurement is comparable to R2's rather than to a differently-shaped prompt;
* the block count is **19** (PANEL-B's), not 112 (PANEL-A's) -- the spec warns
  about this by name;
* `R2-Qwen3` is a NEW arm with a two-condition decision rule, and a pass on the
  performance condition alone is `CONDITIONAL_ON_LAP`, never `ADOPTED`;
* the wall-time arithmetic comes from R2's own measured token counts, and its
  conclusion (25.6 days against the incumbent's 3.9 hours, at the contended
  rate) is the reason the idle re-measurement exists.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.portfolio_intelligence import r2_trial        # noqa: E402
from scripts import night_l4_qwen3_measure as l4                    # noqa: E402

DOC = REPO / "docs" / "TRIALS" / "TRIAL-R2-monthly-news-digest-read.md"

#: assembled rather than written out, so this file's own text does not trip the
#: scanners that look for these names in source
_SHELL = ("subprocess" + ".run", "subprocess" + ".Popen", "os" + "." + "system")


def _calls(path: Path) -> set[str]:
    """Every dotted call name in executable code. Docstrings are not code."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            parts = []
            while isinstance(f, ast.Attribute):
                parts.append(f.attr)
                f = f.value
            if isinstance(f, ast.Name):
                parts.append(f.id)
            if parts:
                names.add(".".join(reversed(parts)))
    return names


def test_the_job_never_starts_or_stops_the_server():
    calls = _calls(Path(l4.__file__))
    banned = {"llama_server.start", "llama_server.stop", "llama_server.bind_lifetime",
              "llama_server.stop_if_owned", "start", "stop"}
    hit = sorted(c for c in calls if c in banned)
    assert not hit, (
        f"L4 calls {hit}. The desktop shell owns llama-server's lifetime; this job asks and "
        "never sequences.")
    shell = sorted(c for c in calls if c in _SHELL)
    assert not shell, f"L4 reaches the shell via {shell}, which is a start by another name"


def test_the_reader_state_is_read_not_changed():
    st = l4.reader_state()
    for k in ("listening", "ready", "pid", "vram", "detail"):
        assert k in st
    assert "owns llama-server's lifetime" in st["this_job_never_starts_or_stops_it"]


def test_the_file_check_reports_absence_as_absence():
    fc = l4.file_check(with_hash=False)
    assert fc["expected_file"] == l4.GGUF_FILE
    assert fc["license"] == "apache-2.0"
    assert isinstance(fc["present"], bool)
    if not fc["present"]:
        assert fc["sha256"] is None and fc["status"].startswith("ABSENT")
    else:
        assert fc["bytes"] > 0 and fc["gibibytes"] > 0
        assert "17.28" in fc["size_note"], (
            "GB and GiB must be reconciled in the receipt -- otherwise a later reader sees "
            "18.56 against the handoff's 17.28 and concludes the file changed")


def test_the_protocol_uses_r2s_frozen_prompts_by_hash():
    p = l4.protocol()
    fp = p["frozen_prompts"]
    assert fp["system_sha256"] == r2_trial.SYSTEM_SHA256
    assert fp["prompt_sha256"] == r2_trial.PROMPT_SHA256
    assert fp["digest_spec_sha256"] == r2_trial.DIGEST_SPEC_SHA256


def test_the_sweep_is_the_roadmaps_own_and_has_a_stop_condition():
    p = l4.protocol()["step_2_sweep"]
    assert p["n_cpu_moe"] == [48, 40, 32, 24]
    assert "AEGIS_LLAMA_N_CPU_MOE" in p["env"]
    assert "never taskkill" in p["between_settings"]
    assert "6866" in p["stop_condition"] or "6,866" in p["stop_condition"]
    assert "prompt-eval" in p["decisive_number"]


def test_the_block_count_is_panel_bs_nineteen_and_says_it_is_not_112():
    reg = l4.protocol()["step_4_registration"]
    assert "19 monthly blocks" in reg["block_count"]
    assert "112" in reg["block_count"] and "PANEL-A" in reg["block_count"]


def test_the_refusal_definition_reuses_the_language_pin():
    step = l4.protocol()["step_3_refusal_rate"]
    assert step["n_digests"] == 200
    assert any("llm_language.refuse" in s for s in step["a_refusal_is"])
    assert "PLAIN Instruct" in step["build"]
    assert "not to" in step["compared_to"] and "zero" in step["compared_to"]


def test_adoption_needs_the_lookahead_condition_too():
    rule = l4.protocol()["step_5_decision_rule"]
    assert len(rule["adopt_only_if"]) == 2
    assert any("Lookahead" in s for s in rule["adopt_only_if"])
    assert rule["a_pass_on_the_first_alone_is"].startswith("CONDITIONAL_ON_LAP")


def test_the_wall_time_comes_from_r2s_own_measured_tokens():
    wt = l4.wall_time()
    assert wt["mean_prompt_tokens"] == pytest.approx(330.4, abs=0.2)
    assert wt["mean_completion_tokens"] == pytest.approx(14.0, abs=0.2)
    assert wt["panelB_calls_arm_plus_control"] == 37002
    assert wt["incumbent_qwen2_5_7b"]["panelB_hours"] == pytest.approx(3.9, abs=0.1)
    slow = wt["qwen3_30b_a3b_at_the_CONTENDED_rates"]
    assert slow["panelB_days"] > 10, (
        "the contended arithmetic no longer says this arm is impractical, which is the whole "
        "reason the idle re-measurement is the first step")
    assert "Not guessed" in wt["source"]


# ---------------------------------------------------------------------------
# the registration
# ---------------------------------------------------------------------------
def _doc() -> str:
    if not DOC.is_file():
        pytest.skip(f"trial doc absent on this machine: {DOC}")
    return DOC.read_text(encoding="utf-8", errors="replace")


def test_the_addendum_registers_a_new_arm_and_says_it_is_unsigned():
    d = _doc()
    assert "ADDENDUM (UNSIGNED)" in d
    assert "`R2-Qwen3`, a NEW ARM beside R2" in d
    assert "no Qwen3 digest has been read" in d
    assert "19 monthly blocks" in d and "not 112" in d
    assert "CONDITIONAL_ON_LAP" in d


def test_the_addendum_carries_the_models_sha256_and_leaves_the_incumbents_alone():
    d = _doc()
    fc = l4.file_check(with_hash=False)
    if fc["present"]:
        assert "6c997b8af17debdfb01d890214400ccbab00db6acc0ba8da5de1cc906c4774d0" in d
    assert r2_trial.MODEL_IDENTITY["sha256"] in d, (
        "the incumbent's model hash left the document -- a new arm must be registered BESIDE "
        "R2, never on top of it")
    assert "apache-2.0" in d


def test_the_receipt_refuses_by_name_when_the_reader_is_down():
    night = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-13"
    path = night / "L4_qwen3_measure_run01.json"
    if not path.is_file():
        pytest.skip("L4 has not run on this checkout")
    r = json.loads(path.read_text(encoding="utf-8"))
    assert r["status"] in ("PENDING_MODEL", "REFUSED")
    assert r["arm"] == "R2-Qwen3"
    assert r["stage"] == "raw"
    assert r["llm_spend_usd"] == 0.0, "L4 must not have spent a cent -- it made no model call"
    assert r["reader"]["ready"] is False or r["status"] == "REFUSED"
    assert r["protocol"]["frozen_prompts"]["prompt_sha256"] == r2_trial.PROMPT_SHA256
    assert r["next_test"]
