"""The LLM must answer in English, and a reply that does not is REFUSED.

WHY THIS EXISTS. `deepseek-chat` code-switches to Chinese on prompts that never
name an output language — reported live 2026-08-24. Somebody had already hit it
and fixed it in exactly one place: `explain_move.py` carries "Always answer in
English" inline in its system prompt. Every other call site — the news summary,
the daily brief, the two-sided argument, the stock outlook, the expectation
generator, the portfolio commentary — had no language instruction at all.

A per-call-site fix for a provider-wide behaviour is how the next call site
inherits the bug, so the pin moved into `_call_llm` and applies to both
providers.

AND THE REASON IT IS NOT MERELY COSMETIC: the arena mints GRADEABLE
PredictionRecords from some of this output. A reply nobody can read that is
passed through anyway does not produce an ugly summary — it produces a forward
evidence row that cannot be re-collected and cannot be graded.
"""

from __future__ import annotations

import pytest

from backend.services import llm_analyzer as la


# ── the detector ────────────────────────────────────────────────────────────


ENGLISH = "Apple rose 3% on stronger than expected iPhone demand this quarter."
CHINESE = "苹果公司股价上涨因为需求强劲"
JAPANESE = "アップルの株価は上昇しました"
RUSSIAN = "Акции выросли на три процента"


def test_plain_english_is_not_flagged():
    assert la._non_latin_share(ENGLISH) == 0.0


@pytest.mark.parametrize("text", [CHINESE, JAPANESE, RUSSIAN])
def test_a_reply_in_another_script_is_flagged(text):
    assert la._non_latin_share(text) > la._NON_LATIN_BAR


def test_an_english_reply_QUOTING_a_foreign_name_is_kept():
    """A share, not 'contains a CJK character'. A legitimate reply may quote a
    company name or a ticker, and refusing that would be a guard that fires on
    correct output — the most expensive kind."""
    mixed = f"Apple ({CHINESE[:2]}) rose 3% today on strong regional demand."
    assert la._non_latin_share(mixed) < la._NON_LATIN_BAR
    assert la._refuse_non_english("deepseek", "t", mixed) is False


def test_an_empty_reply_is_not_a_LANGUAGE_failure():
    """Empty is a different failure with a different fallback, and conflating
    them would make the refusal counter unreadable."""
    assert la._non_latin_share("") == 0.0
    assert la._refuse_non_english("deepseek", "t", "") is False


def test_a_numbers_only_reply_is_not_flagged():
    assert la._non_latin_share("3.2% / 14.7 / -0.05") == 0.0


# ── the refusal ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_counters():
    before = dict(la._LANGUAGE_REFUSALS)
    la._LANGUAGE_REFUSALS.clear()
    yield
    la._LANGUAGE_REFUSALS.clear()
    la._LANGUAGE_REFUSALS.update(before)


def test_a_refusal_is_COUNTED_per_provider_not_just_logged():
    """A rate is what decides whether a provider is fit for gradeable records,
    and a log nobody aggregates cannot produce one."""
    assert la._refuse_non_english("deepseek", "news", CHINESE) is True
    assert la._refuse_non_english("deepseek", "brief", JAPANESE) is True
    assert la._refuse_non_english("anthropic", "news", RUSSIAN) is True
    assert la.language_refusals() == {"deepseek": 2, "anthropic": 1}


def test_the_refusal_count_is_on_the_usage_surface():
    """Otherwise the failure is silent: the caller falls back to its template
    and the page still renders."""
    la._refuse_non_english("deepseek", "news", CHINESE)
    assert la.llm_usage()["language_refusals"] == {"deepseek": 1}


# ── the pin ─────────────────────────────────────────────────────────────────


def test_the_language_pin_is_appended_to_BOTH_provider_paths():
    """Pinned by reading the source, because the alternative is a live call.
    If a third provider is added and does not carry the pin, this fails."""
    import inspect

    src = inspect.getsource(la._call_llm)
    # every system prompt handed to a provider must carry the pin
    assert src.count("system_prompt + _LANGUAGE_PIN") == 2, (
        "a provider path is sending an un-pinned system prompt")
    assert "english" in la._LANGUAGE_PIN.lower()


def test_the_pin_does_not_replace_the_callers_own_instructions():
    """It appends. A pin that overwrote the caller's system prompt would fix
    the language and break every contract built on top of it."""
    assert la._LANGUAGE_PIN.startswith(" ")
    assert len(la._LANGUAGE_PIN) < 60
