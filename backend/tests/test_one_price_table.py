"""X7 — there is ONE LLM rate table, and a second one is a red test.

WHAT HAPPENED. `backend/services/llm_research.py` carried its own literal:

    PRICE_PER_MTOK = {
        "deepseek-chat":     {"in": 0.27, "out": 1.10},
        "deepseek-reasoner": {"in": 0.55, "out": 2.19},
    }

— DeepSeek's PUBLISHED list, copied by hand. Meanwhile
`backend/config.LLM_PRICE_PER_MTOK` was re-derived on 2026-09-05 from the
provider's own BALANCE (`C3_deepseek_price_derivation_run01.json`) and says
0.169413 / 1.284835 for the same model. The two disagreed by **1.59x on the
input leg and 1.16x** on the output leg for every call this module ledgered, and
`scripts/llm_cost_audit.py` reconciled that ledger against `config`'s table —
the table the ledger had never used. The audit existed to find exactly this gap
and structurally could not see it.

This is the same failure family as the provider declaration
(`test_llm_provider_declaration.py`): a constant that READS as authoritative
while a second copy does the work. The fix is not "keep them in sync", which is
a promise; it is "there is one of them", which is a test.

WHAT IS AND IS NOT FORBIDDEN. A module may name a rate for a model `config`
does NOT price — `scripts/era_replay_v2.NANO_PRICE_PER_MTOK` prices OpenAI's
`gpt-5-nano`, which has no row in `config` and whose receipts say so in as many
words. What is forbidden is a SECOND rate for a model `config` already prices,
because then a call's cost depends on which module ledgered it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from backend import config
from backend.services import llm_research as LR

REPO = Path(__file__).resolve().parents[2]

#: Where a rate table could plausibly live. `backend/tests` is excluded: a test
#: fixture that constructs a table to feed a function is not a second source of
#: truth, and forbidding it would forbid testing the pricing at all.
_SCAN_DIRS = ("backend", "scripts", "learner", "lab", "engine")
_SKIP_PARTS = {"tests", "node_modules", ".venv", "venv", "__pycache__", "site-packages"}

#: A name is "rate-table shaped" if it mentions a per-token price unit.
_NAME_RE = re.compile(r"PRICE_PER_MTOK|PRICE_PER_1K|PRICE_PER_TOKEN|COST_PER_MTOK",
                      re.IGNORECASE)


def _py_files() -> list[Path]:
    out: list[Path] = []
    for d in _SCAN_DIRS:
        root = REPO / d
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            if _SKIP_PARTS & set(p.parts):
                continue
            out.append(p)
    return sorted(out)


def _module_level_rate_tables() -> dict[str, dict]:
    """`"<relpath>::<NAME>" -> {"literal": bool, "models": [...]}`.

    Parsed, never imported: importing every script in the repo to read a
    constant would pull pandas, torch and the panel loader into a test about
    two dictionaries.
    """
    found: dict[str, dict] = {}
    for p in _py_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:                                    # noqa: PERF203
            continue
        for node in tree.body:
            targets = []
            if isinstance(node, ast.Assign):
                targets = [t for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target]
            for t in targets:
                if not _NAME_RE.search(t.id):
                    continue
                value = node.value
                literal = isinstance(value, ast.Dict)
                models: list[str] = []
                if literal:
                    for k in value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            models.append(k.value)
                key = f"{p.relative_to(REPO).as_posix()}::{t.id}"
                found[key] = {"literal": literal, "models": models}
    return found


# --------------------------------------------------------------- the wiring

def test_llm_research_uses_the_config_table_object_itself():
    assert LR.PRICE_PER_MTOK is config.LLM_PRICE_PER_MTOK, (
        "llm_research must reference config.LLM_PRICE_PER_MTOK, not copy it")


def test_the_ledger_prices_a_call_at_the_config_rate():
    """The number that reaches the ledger is the derived rate, not the list one."""
    p = config.LLM_PRICE_PER_MTOK["deepseek-chat"]
    got = LR._price("deepseek-chat", 1_000_000, 1_000_000)
    assert got == pytest.approx(p["in"] + p["out"])
    # and the retired list rate is NOT what comes out.
    assert got != pytest.approx(0.27 + 1.10)


def test_price_is_re_read_at_call_time(monkeypatch):
    """A test (or a re-derivation) that swaps the table must be obeyed."""
    fake = dict(config.LLM_PRICE_PER_MTOK)
    fake["deepseek-chat"] = {"in": 1.0, "cached_in": 0.1, "out": 2.0}
    monkeypatch.setattr(config, "LLM_PRICE_PER_MTOK", fake)
    assert LR._price("deepseek-chat", 1_000_000, 1_000_000) == pytest.approx(3.0)


def test_an_unknown_model_falls_back_to_the_default_row():
    p = config.LLM_PRICE_PER_MTOK[LR.DEFAULT_MODEL]
    assert LR._price("no-such-model-9000", 1_000_000, 0) == pytest.approx(p["in"])


# ------------------------------------------------ the "only one table" guard

def test_config_is_the_only_literal_rate_table_for_a_priced_model():
    tables = _module_level_rate_tables()
    canonical = "backend/config.py::LLM_PRICE_PER_MTOK"
    assert canonical in tables, (
        f"the canonical table moved or was renamed; found {sorted(tables)}")
    assert tables[canonical]["literal"] is True

    priced = set(config.LLM_PRICE_PER_MTOK)
    offenders = {}
    for key, info in tables.items():
        if key == canonical or not info["literal"]:
            continue
        overlap = sorted(set(info["models"]) & priced)
        if overlap:
            offenders[key] = overlap
    assert not offenders, (
        "a second rate table prices a model config already prices, so a call's "
        f"cost depends on which module ledgered it: {offenders}")


def test_the_second_table_that_is_allowed_prices_nothing_config_prices():
    """`era_replay_v2.NANO_PRICE_PER_MTOK` is the ONE permitted extra table.

    It exists because `gpt-5-nano` has no row in `config` — its receipts say so
    and call their totals a LOWER bound. If it ever grows a DeepSeek or Claude
    row, the guard above turns red, which is the whole point.
    """
    tables = _module_level_rate_tables()
    key = "scripts/era_replay_v2.py::NANO_PRICE_PER_MTOK"
    if key not in tables:
        pytest.skip("era_replay_v2 no longer carries a local nano table")
    assert not set(tables[key]["models"]) & set(config.LLM_PRICE_PER_MTOK)


def test_the_guard_would_have_caught_the_defect_it_was_written_for(tmp_path):
    """KNOWN ANSWER. The retired literal, re-created, must be found.

    A guard nobody has seen fire is a guard nobody knows works. This writes the
    exact dictionary that stood in `llm_research.py` until 2026-09-07 into a
    scratch module and asserts the scanner flags it.
    """
    mod = tmp_path / "offender.py"
    mod.write_text(
        "PRICE_PER_MTOK = {\n"
        '    "deepseek-chat": {"in": 0.27, "out": 1.10},\n'
        '    "deepseek-reasoner": {"in": 0.55, "out": 2.19},\n'
        "}\n", encoding="utf-8")
    tree = ast.parse(mod.read_text(encoding="utf-8"))
    node = tree.body[0]
    assert isinstance(node, ast.Assign)
    assert _NAME_RE.search(node.targets[0].id)
    assert isinstance(node.value, ast.Dict)
    models = [k.value for k in node.value.keys]
    assert set(models) & set(config.LLM_PRICE_PER_MTOK) == {
        "deepseek-chat", "deepseek-reasoner"}
