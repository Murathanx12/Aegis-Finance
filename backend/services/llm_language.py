"""One output-language contract for every LLM call site in the repository.

WHY THIS IS ITS OWN MODULE, AND THE MISTAKE IT EXISTS TO STOP REPEATING
======================================================================
`deepseek-chat` code-switches to Chinese when the system prompt does not name an
output language. That was reported live on 2026-08-24, and the repository's
first response to it — months earlier — was to add "Always answer in English"
inline in ONE system prompt, in `explain_move.py`. Every other caller inherited
the bug.

The second response, the same day, was to fix it centrally in
`llm_analyzer._call_llm`. That was better and it was still wrong, because
`llm_analyzer` is not the only path to the vendor: **seven modules call
`chat.completions.create` directly** —

    architecture_arena · copilot · leakage_probe · llm_swarm
    optimus_specialists · why_moved · llm_analyzer

so a fix inside one of them protects one of seven. That is the same per-call-site
mistake one level up, made by the session that had just written the comment
criticising it.

So the contract lives here, once, and every call site imports it. A new call
site that forgets is a test failure: `test_llm_language_contract.py` enumerates
the direct-client modules from the source tree and asserts each one applies it.

WHAT THE CONTRACT IS
====================
`pin(system)` appends the language instruction. `refuse(provider, purpose,
text)` measures the SHARE of letters in non-Latin scripts and returns True when
the reply should be discarded — a share rather than "contains a CJK character",
because a legitimate reply may quote a company name and a guard that fires on
correct output is the expensive kind.

REFUSED, NOT REPAIRED AND NOT RETRIED. The callers already fall back to
deterministic paths when the LLM returns nothing, so a refusal degrades to
behaviour that already exists; a retry doubles spend on exactly the calls that
are failing, against a small prepaid balance; and the arena mints GRADEABLE
PredictionRecords from some of this output, so a reply nobody can read that is
passed through anyway does not produce a bad summary — it produces a forward
evidence row that cannot be re-collected and cannot be graded.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Appended to every system prompt, whatever the provider or the call site.
LANGUAGE_PIN = " Respond in English only."

#: Scripts that mean the reply is not the English the caller asked for.
#: CJK, Hangul, Cyrillic, Arabic, Hebrew, Devanagari, Thai.
_NON_LATIN = (
    (0x0400, 0x04FF), (0x0590, 0x05FF), (0x0600, 0x06FF), (0x0900, 0x097F),
    (0x0E00, 0x0E7F), (0x1100, 0x11FF), (0x3040, 0x30FF), (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF),
)

#: Above this share of letters the reply is refused. Deliberately not zero.
NON_LATIN_BAR = 0.10

#: Refusals by provider. A counter and not only a log line: a RATE is what
#: decides whether a provider is fit for gradeable records, and a log nobody
#: aggregates cannot produce one.
REFUSALS: dict[str, int] = {}


def pin(system_prompt: str) -> str:
    """The system prompt, with the output language named."""
    return f"{system_prompt or ''}{LANGUAGE_PIN}"


def pin_messages(messages: list) -> list:
    """Pin the language on an already-assembled `messages` list.

    Some call sites build the whole array before the request (a chat history, a
    multi-turn arena transcript). This appends to the FIRST system entry and
    leaves everything else byte-identical; if there is no system entry it
    prepends one, because a call with no system message is exactly the case
    where the model picks its own language.
    """
    out = [dict(m) for m in (messages or [])]
    for m in out:
        if m.get("role") == "system":
            m["content"] = pin(str(m.get("content") or ""))
            return out
    return [{"role": "system", "content": LANGUAGE_PIN.strip()}] + out


def non_latin_share(text: str) -> float:
    """Fraction of LETTERS sitting in a non-Latin script. Digits and
    punctuation are ignored, so a numeric reply scores 0."""
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return 0.0
    hits = sum(1 for c in letters
               if any(lo <= ord(c) <= hi for lo, hi in _NON_LATIN))
    return hits / len(letters)


def refuse(provider: str, purpose: str, text: str) -> bool:
    """True when the reply is mostly not English and must be discarded."""
    share = non_latin_share(text)
    if share <= NON_LATIN_BAR:
        return False
    REFUSALS[provider] = REFUSALS.get(provider, 0) + 1
    logger.warning(
        "LLM reply refused: %.0f%% non-Latin script from %s (purpose=%s). "
        "Discarded; the caller falls back. Count for this provider: %d",
        share * 100, provider, purpose, REFUSALS[provider])
    return True


def refusals() -> dict:
    """Per-provider count of replies refused for not being English."""
    return dict(REFUSALS)


#: Modules that build their own OpenAI-compatible client and call
#: `chat.completions.create` directly rather than going through
#: `llm_analyzer._call_llm`. Enumerated so the contract test can assert each one
#: applies the pin — a new direct call site that forgets is a red suite, not a
#: discovery when somebody notices Chinese in a dashboard.
DIRECT_CALL_SITES = (
    "architecture_arena", "copilot", "leakage_probe", "llm_swarm",
    "llm_analyzer", "optimus_specialists", "why_moved",
)

#: Call sites deliberately NOT yet wired, with the reason. Empty is the goal.
#: An exemption with a date and a reason is a decision; an exemption without one
#: is a module somebody forgot.
DEFERRED: dict[str, str] = {
    "why_moved": (
        "2026-08-24: `pi_why_moved` fires tonight at 17:15 ET and is the P0 "
        "being waited on — `live_forward` has been quiet 12 days. Editing the "
        "module hours before the run it has to survive is a risk with no "
        "upside tonight; the guard degrades to the deterministic fallback "
        "anyway. Wire it after the run is confirmed."),
}
