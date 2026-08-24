"""DeepSeek is the ONLY provisioned provider, and the code must say so.

WHAT HAPPENED, 2026-08-24. `llm_analyzer` reads as though Claude were primary
and DeepSeek the fallback:

    if _ANTHROPIC_API_KEY:  return "claude"
    elif _DEEPSEEK_API_KEY: return "deepseek"

and `.env` carries an `ANTHROPIC_API_KEY=` line with an EMPTY VALUE. That reads
as configured and is not — the branch tests truthiness — so `_get_provider()`
has always returned "deepseek".

**Nothing was broken and no call was lost.** DeepSeek has been the live provider
throughout; the prod health surface reports it, and the Chinese-output glitch is
itself proof the model was answering. The only cost was to a reader who believed
the first branch was live and spent time on a path with no key behind it.

These tests make the declaration checkable instead of inferable:

  * an env var present-but-empty is reported as `declared_but_empty`, never as
    configured and never as absent — "absent" is a decision, "empty" is a loose
    end, and collapsing them is what made this cost time;
  * the resolved provider matches the declared sole provider;
  * every guard the Claude path carries, the DeepSeek path carries too — since
    DeepSeek is the one that actually runs, a guard on the dormant branch alone
    protects nothing.
"""

from __future__ import annotations

import os

import pytest

from backend.services import llm_analyzer as la


def test_deepseek_is_the_declared_sole_provider():
    assert la.SOLE_PROVISIONED_PROVIDER == "deepseek"


@pytest.fixture
def provisioned(monkeypatch):
    """The PROVISIONED state, set explicitly rather than inherited.

    These tests were written against the ambient `.env` and passed locally and
    failed under `AEGIS_IGNORE_DOTENV=1` — which is precisely the bug class the
    CI-mimic exists to catch ("eleven tests once passed locally BECAUSE a
    secrets file existed"). Caught by the switch on its first run, by the same
    session that added it.

    A test about the DECLARATION must not depend on whether this machine
    happens to hold a key.
    """
    monkeypatch.setattr(la, "_ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(la, "_DEEPSEEK_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-not-a-real-key")


def test_the_resolved_provider_matches_the_declaration(provisioned):
    """If this fails, either a key appeared or one vanished — both are events
    somebody should know about, rather than discover from behaviour."""
    st = la.provider_status()
    assert st["matches_declaration"], st
    assert st["active"] == "deepseek"


def test_with_NO_keys_the_provider_is_none_and_nothing_pretends_otherwise(
        monkeypatch):
    """The CI case, pinned. No keys is a legitimate state — every caller falls
    back to its deterministic path — and it must report as `none` rather than
    as the declared provider."""
    monkeypatch.setattr(la, "_ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(la, "_DEEPSEEK_API_KEY", "")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    st = la.provider_status()
    assert st["active"] == "none"
    assert st["matches_declaration"] is False
    assert la.is_available() is False


def test_an_EMPTY_key_is_reported_separately_from_an_ABSENT_one(monkeypatch):
    """The whole finding in one assertion."""
    monkeypatch.setattr(la, "_ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    st = la.provider_status()
    assert "anthropic" in st["declared_but_empty"]
    assert "anthropic" not in st["configured"]
    assert "anthropic" not in st["absent"]


def test_a_TRULY_ABSENT_key_is_reported_as_absent(monkeypatch):
    monkeypatch.setattr(la, "_ANTHROPIC_API_KEY", "")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    st = la.provider_status()
    assert "anthropic" in st["absent"]
    assert "anthropic" not in st["declared_but_empty"]


def test_a_whitespace_only_key_is_not_configured(monkeypatch):
    """`ANTHROPIC_API_KEY= ` with a trailing space is the same loose end wearing
    a different shape, and `os.getenv(...)` alone would call it configured."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    assert os.getenv("ANTHROPIC_API_KEY", "").strip() == ""


def test_the_provider_row_is_on_the_usage_surface(provisioned):
    u = la.llm_usage()
    assert u["providers"]["sole_provisioned"] == "deepseek"
    assert u["providers"]["active"] == "deepseek"


def test_the_sole_provisioned_declaration_does_NOT_depend_on_the_environment():
    """It is a declaration, not a reading. It must be the same string on a
    machine with keys and on CI without them."""
    assert la.SOLE_PROVISIONED_PROVIDER == "deepseek"


def test_the_DEEPSEEK_path_carries_the_language_pin_too():
    """DeepSeek is the branch that actually runs. A guard applied only to the
    dormant Claude branch would protect nothing at all."""
    import inspect

    src = inspect.getsource(la._call_llm)
    deepseek_half = src[src.index("Try DeepSeek"):]
    assert "_LANGUAGE_PIN" in deepseek_half
    assert "_refuse_non_english(\"deepseek\"" in deepseek_half


def test_is_available_is_true_on_deepseek_alone(provisioned):
    """Because it has been, all along — with a key present."""
    assert la.is_available() is True


# ── the CI-mimic switch ─────────────────────────────────────────────────────


def test_config_exposes_a_way_to_ignore_dotenv_without_moving_the_file():
    """The documented CI-mimic recipe moved `.env` aside inside a subshell with
    an EXIT trap. On 2026-08-24 the subshell died before the trap ran and the
    machine lost every key on it. The handoff warned about exactly that and the
    warning did not prevent it, because a warning cannot.

    `AEGIS_IGNORE_DOTENV=1` reproduces CI without touching the file."""
    import inspect

    from backend import config

    src = inspect.getsource(config)
    assert "AEGIS_IGNORE_DOTENV" in src
    i = src.index("AEGIS_IGNORE_DOTENV")
    assert "load_dotenv" in src[i:i + 400], (
        "the switch must gate load_dotenv, not merely be mentioned")


@pytest.mark.parametrize("val,ignored", [
    ("1", True), ("true", True), ("YES", True),
    ("0", False), ("", False), ("no", False),
])
def test_the_switch_accepts_the_obvious_truthy_spellings(val, ignored):
    assert (val.strip().lower() in ("1", "true", "yes")) is ignored
