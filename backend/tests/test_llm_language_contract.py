"""EVERY path to the vendor pins the output language — enumerated, not assumed.

THE MISTAKE THIS PINS, WHICH WAS MADE TWICE IN ONE DAY.

`deepseek-chat` code-switches to Chinese when the system prompt does not name an
output language. The repository's first fix put "Always answer in English"
inline in ONE prompt (`explain_move.py`); every other caller inherited the bug.
The second fix, hours before this file was written, moved the pin into
`llm_analyzer._call_llm` — better, and still wrong, because **seven modules
build their own OpenAI-compatible client and call `chat.completions.create`
directly**. A fix inside one of them protects one of seven.

So the contract lives in `llm_language` and this test walks the SOURCE TREE to
find every direct call site. A new module that opens its own client and forgets
the pin is a red suite, not a discovery when somebody notices Chinese in a
dashboard three weeks later — the same rule `signal_reachability` enforces for
modules, applied to prompts.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

from backend.services import llm_language as L

SERVICES = Path(__file__).resolve().parents[1] / "services"


def _attr_path(node: ast.AST) -> str:
    """`a.b.c` for a nested Attribute chain, else ""."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _direct_call_sites() -> set[str]:
    """Modules under `services/` that CALL `chat.completions.create`.

    Found by walking the AST rather than grepping the text: the first version
    matched `llm_language` itself, because its docstring NAMES the call it
    exists to talk about. A detector that cannot tell code from prose is the
    kind that gets an exemption added to shut it up.
    """
    found = set()
    for p in SERVICES.rglob("*.py"):
        try:
            tree = ast.parse(io.open(p, encoding="utf-8").read())
        except Exception:                                    # noqa: BLE001
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                path = _attr_path(node.func)
                if path.endswith("chat.completions.create"):
                    found.add(p.stem)
                    break
    return found


# ── the enumeration is real, not a hand-maintained list ─────────────────────


def test_the_declared_call_sites_match_what_the_SOURCE_TREE_contains():
    """A hand-maintained list drifts silently; this one cannot."""
    actual = _direct_call_sites()
    declared = set(L.DIRECT_CALL_SITES)
    assert actual == declared, (
        f"undeclared direct call sites: {sorted(actual - declared)}; "
        f"declared but gone: {sorted(declared - actual)}. Add the module to "
        f"llm_language.DIRECT_CALL_SITES and wire the pin, or remove it.")


@pytest.mark.parametrize("mod", sorted(set(L.DIRECT_CALL_SITES)))
def test_every_direct_call_site_applies_the_language_pin(mod):
    if mod in L.DEFERRED:
        pytest.skip(f"deferred: {L.DEFERRED[mod][:80]}")
    src = io.open(SERVICES / f"{mod}.py", encoding="utf-8").read()
    applied = ("_lang.pin(" in src or "_lang.pin_messages(" in src
               or "_LANGUAGE_PIN" in src)
    assert applied, (
        f"{mod} calls chat.completions.create without pinning the output "
        f"language. Use llm_language.pin(system) or pin_messages(messages).")


def test_a_deferred_call_site_carries_a_REASON_and_a_DATE():
    """An exemption with a reason is a decision; one without is a module
    somebody forgot. Empty is the goal."""
    for mod, reason in L.DEFERRED.items():
        assert mod in L.DIRECT_CALL_SITES, f"{mod} deferred but not a call site"
        assert len(reason) > 60, f"{mod}: reason too thin to be a decision"
        assert "2026-" in reason, f"{mod}: no date on the exemption"


# ── the contract itself ─────────────────────────────────────────────────────


def test_pin_appends_and_does_not_replace():
    """A pin that overwrote the caller's system prompt would fix the language
    and break every contract built on top of it."""
    assert L.pin("Be terse.") == "Be terse. Respond in English only."
    assert L.pin("").strip() == "Respond in English only."


def test_pin_messages_edits_only_the_system_entry():
    msgs = [{"role": "system", "content": "S"},
            {"role": "user", "content": "U"},
            {"role": "assistant", "content": "A"}]
    out = L.pin_messages(msgs)
    assert out[0]["content"] == "S Respond in English only."
    assert out[1] == msgs[1] and out[2] == msgs[2]
    assert msgs[0]["content"] == "S", "must not mutate the caller's list"


def test_pin_messages_PREPENDS_when_there_is_no_system_entry():
    """A call with no system message is exactly the case where the model picks
    its own language."""
    out = L.pin_messages([{"role": "user", "content": "U"}])
    assert out[0]["role"] == "system"
    assert "English" in out[0]["content"]
    assert out[1]["role"] == "user"


def test_pin_messages_survives_an_empty_list():
    assert L.pin_messages([])[0]["role"] == "system"
    assert L.pin_messages(None)[0]["role"] == "system"


# ── one counter, program-wide ───────────────────────────────────────────────


def test_llm_analyzer_shares_the_ONE_counter():
    """Every call site increments the same dict, or the rate is per-module and
    means nothing."""
    from backend.services import llm_analyzer as la
    assert la._LANGUAGE_REFUSALS is L.REFUSALS
    assert la._LANGUAGE_PIN == L.LANGUAGE_PIN
    assert la._NON_LATIN_BAR == L.NON_LATIN_BAR


def test_the_bar_is_a_share_so_a_quoted_foreign_name_survives():
    before = dict(L.REFUSALS)
    try:
        L.REFUSALS.clear()
        assert L.refuse("deepseek", "t", "苹果公司股价上涨因为需求强劲") is True
        assert L.refuse("deepseek", "t",
                        "Apple (苹果) rose 3% on strong regional demand today"
                        ) is False
        assert L.refusals() == {"deepseek": 1}
    finally:
        L.REFUSALS.clear()
        L.REFUSALS.update(before)
